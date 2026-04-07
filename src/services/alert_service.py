"""
Alert Generation Service

This service monitors active watchlists and generates alerts for high-risk flights.
Can be run as a background service or cron job.
"""

import sys
import os
import time
import logging
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from dotenv import load_dotenv
load_dotenv()

from src.database.models import init_db, User, Watchlist, Alert, UserPreferences
from src.data.fetch_opensky import fetch_flights
from src.data.fetch_weather import WeatherService
from src.features.build_features import build_featured_flights

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class AlertGenerationService:
    """Service to monitor watchlists and generate alerts."""
    
    def __init__(self):
        """Initialize the alert service."""
        self.engine, self.SessionLocal = init_db()
        self.weather_service = self._init_weather_service()
        self.check_interval = int(os.environ.get('ALERT_CHECK_INTERVAL', 300))  # 5 minutes default
        logger.info(f"Alert service initialized (check interval: {self.check_interval}s)")
    
    def _init_weather_service(self):
        """Initialize weather service."""
        try:
            api_key = os.environ.get('OPENWEATHER_API_KEY')
            if api_key:
                return WeatherService(api_key)
        except Exception as e:
            logger.warning(f"Weather service unavailable: {e}")
        return None
    
    def check_watchlists(self):
        """Check all active watchlists and generate alerts."""
        db = self.SessionLocal()
        
        try:
            # Get all active watchlists
            watchlists = db.query(Watchlist).filter(Watchlist.is_active == True).all()
            logger.info(f"Checking {len(watchlists)} active watchlists")
            
            for watchlist in watchlists:
                try:
                    self.process_watchlist(db, watchlist)
                except Exception as e:
                    logger.error(f"Error processing watchlist {watchlist.id}: {e}")
            
            db.commit()
            logger.info("Watchlist check complete")
            
        except Exception as e:
            logger.error(f"Error checking watchlists: {e}")
            db.rollback()
        finally:
            db.close()
    
    def process_watchlist(self, db, watchlist):
        """Process a single watchlist and generate alerts if needed."""
        # Get user preferences
        user = db.query(User).filter(User.id == watchlist.user_id).first()
        if not user or not user.is_active:
            logger.debug(f"Skipping watchlist {watchlist.id} - user inactive")
            return
        
        preferences = db.query(UserPreferences).filter(
            UserPreferences.user_id == user.id
        ).first()
        
        if not preferences:
            logger.debug(f"Skipping watchlist {watchlist.id} - no preferences")
            return
        
        # Parse bbox
        try:
            bbox_parts = [float(x.strip()) for x in watchlist.bbox.split(',')]
            if len(bbox_parts) != 4:
                raise ValueError("Invalid bbox format")
            bbox = tuple(bbox_parts)
        except Exception as e:
            logger.error(f"Invalid bbox for watchlist {watchlist.id}: {e}")
            return
        
        # Fetch flights in the watchlist region
        try:
            raw_flights = fetch_flights(bbox=bbox)
            if raw_flights.empty:
                logger.debug(f"No flights in watchlist {watchlist.id} region")
                return
            
            # Add weather data if available
            if self.weather_service:
                raw_flights = self.weather_service.get_weather_for_flights(raw_flights)
            
            # Build features
            featured_flights = build_featured_flights(raw_flights)
            
            # Filter for high-risk flights based on user's threshold
            risk_threshold = preferences.risk_threshold or 'MEDIUM'
            
            if risk_threshold == 'HIGH':
                high_risk = featured_flights[featured_flights['risk_level'] == 'HIGH']
            elif risk_threshold == 'MEDIUM':
                high_risk = featured_flights[
                    (featured_flights['risk_level'] == 'HIGH') |
                    (featured_flights['risk_level'] == 'MEDIUM')
                ]
            else:  # LOW
                high_risk = featured_flights  # All flights
            
            if high_risk.empty:
                logger.debug(f"No high-risk flights in watchlist {watchlist.id}")
                return
            
            # Check alert frequency to avoid spam
            if not self.should_send_alert(db, user.id, watchlist.id, preferences.alert_frequency):
                logger.debug(f"Skipping alert for watchlist {watchlist.id} - frequency limit")
                return
            
            # Generate alert
            self.generate_alert(db, watchlist, high_risk, risk_threshold)
            logger.info(f"Alert generated for watchlist {watchlist.id} ({len(high_risk)} high-risk flights)")
            
        except Exception as e:
            logger.error(f"Error fetching flights for watchlist {watchlist.id}: {e}")
    
    def should_send_alert(self, db, user_id, watchlist_id, frequency):
        """Check if we should send an alert based on frequency setting."""
        if frequency == 'immediate':
            return True
        
        # Get last alert for this watchlist
        last_alert = db.query(Alert).filter(
            Alert.user_id == user_id,
            Alert.watchlist_id == watchlist_id
        ).order_by(Alert.created_at.desc()).first()
        
        if not last_alert:
            return True
        
        # Check time since last alert
        now = datetime.utcnow()
        time_diff = now - last_alert.created_at
        
        if frequency == 'hourly' and time_diff < timedelta(hours=1):
            return False
        elif frequency == 'daily' and time_diff < timedelta(days=1):
            return False
        
        return True
    
    def generate_alert(self, db, watchlist, high_risk_flights, threshold):
        """Generate an alert for high-risk flights."""
        # Determine severity
        high_count = len(high_risk_flights[high_risk_flights['risk_level'] == 'HIGH'])
        
        if high_count >= 5:
            severity = 'HIGH'
        elif high_count >= 1:
            severity = 'MEDIUM'
        else:
            severity = 'LOW'
        
        # Build flight data summary
        flight_summaries = []
        for idx, flight in high_risk_flights.head(10).iterrows():  # Top 10 flights
            flight_summaries.append({
                'callsign': flight['callsign'],
                'icao24': flight['icao24'],
                'origin_country': flight['origin_country'],
                'altitude': float(flight['altitude']) if flight['altitude'] == flight['altitude'] else None,
                'speed_kmh': float(flight['speed_kmh']),
                'risk_level': flight['risk_level'],
                'risk_score': float(flight['risk_score'])
            })
        
        # Create alert
        alert = Alert(
            user_id=watchlist.user_id,
            watchlist_id=watchlist.id,
            alert_type='high_risk_flights',
            severity=severity,
            title=f'High-Risk Flights Detected in {watchlist.name}',
            message=f'Detected {len(high_risk_flights)} flights above {threshold} risk threshold. ' +
                   (f'{high_count} flights are at HIGH risk.' if high_count > 0 else ''),
            flight_data={
                'total_flights': len(high_risk_flights),
                'high_risk_count': high_count,
                'threshold': threshold,
                'flights': flight_summaries
            },
            is_read=False
        )
        
        db.add(alert)
        
        # TODO: Send email notification if enabled
        # if user.preferences.email_alerts:
        #     self.send_email_alert(user, alert)
    
    def run_once(self):
        """Run a single check cycle."""
        logger.info("Starting alert check cycle...")
        self.check_watchlists()
        logger.info("Alert check cycle complete")
    
    def run_forever(self):
        """Run the service continuously."""
        logger.info(f"Alert service running (checking every {self.check_interval}s)")
        logger.info("Press Ctrl+C to stop")
        
        try:
            while True:
                self.run_once()
                time.sleep(self.check_interval)
        except KeyboardInterrupt:
            logger.info("Alert service stopped by user")
        except Exception as e:
            logger.error(f"Alert service error: {e}")

def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='SkyGuard AI Alert Generation Service')
    parser.add_argument('--once', action='store_true', help='Run once and exit')
    parser.add_argument('--interval', type=int, help='Check interval in seconds (default: 300)')
    
    args = parser.parse_args()
    
    # Initialize service
    service = AlertGenerationService()
    
    if args.interval:
        service.check_interval = args.interval
    
    # Run
    if args.once:
        service.run_once()
    else:
        service.run_forever()

if __name__ == "__main__":
    main()
