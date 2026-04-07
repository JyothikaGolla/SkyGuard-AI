"""
Watchlist monitoring service to check for high-risk flights and send alerts.
"""
import logging
from datetime import datetime
from src.database.models import get_db, User, Watchlist, Alert, UserPreferences
from src.data.fetch_opensky import fetch_flights
from src.features.build_features import build_featured_flights
from src.email.email_service import get_email_service

logger = logging.getLogger(__name__)


class WatchlistMonitor:
    """Monitor watchlists and send alerts for high-risk flights."""
    
    def __init__(self):
        """Initialize the watchlist monitor."""
        self.email_service = get_email_service()
    
    def check_all_watchlists(self):
        """
        Check all active watchlists for high-risk flights.
        Creates alerts and sends emails to users with email_alerts enabled.
        
        Returns:
            dict: Statistics about the monitoring run
        """
        stats = {
            'watchlists_checked': 0,
            'alerts_created': 0,
            'emails_sent': 0,
            'errors': 0
        }
        
        db = next(get_db())
        
        try:
            # Get all active watchlists
            watchlists = db.query(Watchlist).filter(Watchlist.is_active == True).all()
            
            logger.info(f"Checking {len(watchlists)} active watchlists")
            
            for watchlist in watchlists:
                try:
                    self._check_watchlist(db, watchlist, stats)
                    stats['watchlists_checked'] += 1
                except Exception as e:
                    logger.error(f"Error checking watchlist {watchlist.id}: {e}")
                    stats['errors'] += 1
            
            db.commit()
            
            logger.info(f"Monitoring complete: {stats}")
            return stats
            
        except Exception as e:
            logger.error(f"Error in watchlist monitoring: {e}")
            db.rollback()
            stats['errors'] += 1
            return stats
        finally:
            db.close()
    
    def _check_watchlist(self, db, watchlist, stats):
        """Check a single watchlist for high-risk flights."""
        # Parse bbox
        try:
            bbox_parts = [float(x.strip()) for x in watchlist.bbox.split(',')]
            if len(bbox_parts) != 4:
                raise ValueError("Invalid bbox format")
            bbox = tuple(bbox_parts)
        except Exception as e:
            logger.error(f"Invalid bbox for watchlist {watchlist.id}: {e}")
            return
        
        # Fetch flights in watchlist region
        try:
            raw_flights = fetch_flights(bbox=bbox)
            if raw_flights.empty:
                return
            
            # Build features
            featured_flights = build_featured_flights(raw_flights)
            
            # Get user preferences
            user = db.query(User).filter(User.id == watchlist.user_id).first()
            if not user:
                return
            
            prefs = db.query(UserPreferences).filter(
                UserPreferences.user_id == user.id
            ).first()
            
            if not prefs:
                return
            
            # Filter high-risk flights based on user's threshold
            risk_threshold = prefs.risk_threshold or 'MEDIUM'
            
            # Define risk levels
            risk_levels = {'LOW': 1, 'MEDIUM': 2, 'HIGH': 3}
            threshold_value = risk_levels.get(risk_threshold, 2)
            
            high_risk_flights = featured_flights[
                featured_flights['risk_level'].apply(
                    lambda x: risk_levels.get(x, 0) >= threshold_value
                )
            ]
            
            if high_risk_flights.empty:
                return
            
            # Collect all alerts for this watchlist check
            new_alerts = []
            
            # Create alerts for high-risk flights
            for _, flight in high_risk_flights.iterrows():
                # Check if alert already exists for this flight (prevent spam)
                existing_alert = db.query(Alert).filter(
                    Alert.user_id == user.id,
                    Alert.flight_data.contains({'icao24': flight['icao24']})
                ).first()
                
                if existing_alert:
                    continue  # Skip if alert already exists
                
                # Create alert
                alert = Alert(
                    user_id=user.id,
                    watchlist_id=watchlist.id,
                    alert_type='high_risk_flight',
                    severity=flight['risk_level'],
                    title=f"High-Risk Flight Detected: {flight['callsign']}",
                    message=f"A {flight['risk_level']} risk flight has been detected in your watchlist '{watchlist.name}'. "
                            f"Risk score: {flight['risk_score']:.2f}",
                    flight_data={
                        'icao24': flight['icao24'],
                        'callsign': flight['callsign'],
                        'origin_country': flight['origin_country'],
                        'risk_score': float(flight['risk_score']),
                        'risk_level': flight['risk_level'],
                        'altitude': float(flight['altitude']) if flight['altitude'] == flight['altitude'] else None,
                        'velocity': float(flight['velocity']) if flight['velocity'] == flight['velocity'] else None,
                    },
                    is_read=False
                )
                
                db.add(alert)
                new_alerts.append({
                    'callsign': flight['callsign'],
                    'icao24': flight['icao24'],
                    'origin_country': flight['origin_country'],
                    'risk_score': float(flight['risk_score']),
                    'risk_level': flight['risk_level'],
                    'altitude': float(flight['altitude']) if flight['altitude'] == flight['altitude'] else None,
                    'velocity': float(flight['velocity']) if flight['velocity'] == flight['velocity'] else None,
                })
                stats['alerts_created'] += 1
            
            # Send ONE email with all alerts for this watchlist (if any new alerts)
            if new_alerts and prefs.email_alerts and self.email_service.is_configured:
                # Check alert frequency preference
                should_send = self._should_send_email(prefs.alert_frequency)
                
                if should_send:
                    email_sent = self.email_service.send_batch_flight_alert(
                        user_email=user.email,
                        user_name=user.full_name or user.username,
                        watchlist_name=watchlist.name,
                        flights=new_alerts
                    )
                    
                    if email_sent:
                        stats['emails_sent'] += 1
            
        except Exception as e:
            logger.error(f"Error fetching flights for watchlist {watchlist.id}: {e}")
            raise
    
    def _should_send_email(self, frequency):
        """
        Determine if email should be sent based on frequency setting.
        
        Args:
            frequency: 'immediate', 'hourly', or 'daily'
        
        Returns:
            bool: True if email should be sent
        """
        # For now, implement immediate only
        # TODO: Implement hourly/daily batching with a separate table to track last sent time
        if frequency == 'immediate':
            return True
        
        # For hourly/daily, you would need to:
        # 1. Store last email sent timestamp per user
        # 2. Check if enough time has passed
        # 3. Batch multiple alerts into one email
        
        return False  # For hourly/daily, implement batching logic


# Global monitor instance
_monitor = None


def get_watchlist_monitor():
    """Get the global watchlist monitor instance."""
    global _monitor
    if _monitor is None:
        _monitor = WatchlistMonitor()
    return _monitor
