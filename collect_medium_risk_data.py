"""
Specialized data collector for MEDIUM-RISK flight scenarios.
Targets flights in moderately challenging conditions:
- Moderate weather (rain/clouds, not severe)
- Slightly elevated vertical rates (5-10 m/s)
- Medium crosswinds (10-20 m/s)
- Moderately low altitude approaches (2000-5000m)
- Fog/low visibility (not severe)
"""
import requests
import pandas as pd
from datetime import datetime, timedelta
import time
import os
from pathlib import Path

# Import weather fetching
import sys
sys.path.append(str(Path(__file__).parent))

# Try to get API key from config
try:
    import config
    WEATHER_API_KEY = config.OPENWEATHER_API_KEY
except (ImportError, AttributeError):
    WEATHER_API_KEY = None  # Will use mock weather data

if WEATHER_API_KEY:
    from src.data.fetch_weather import WeatherService
    weather_service = WeatherService(WEATHER_API_KEY)
else:
    weather_service = None


# Medium-risk flight regions (busy airspace + some weather variety)
MEDIUM_RISK_REGIONS = {
    'europe_busy': (45, 55, 0, 15),                    # Central Europe busy airspace
    'us_northeast': (38, 43, -78, -70),                # US Northeast corridor
    'asia_pacific': (30, 40, 120, 140),                # East Asia busy routes
    'middle_east': (20, 35, 40, 60),                   # Middle East airspace
    'south_america': (-25, -15, -55, -40),             # South America routes
    'africa_north': (25, 35, -5, 10),                  # North Africa
    'canada_south': (43, 50, -85, -70),                # Southern Canada
    'australia_east': (-35, -25, 145, 155),            # Eastern Australia
}


def fetch_flights_bbox(bbox, region_name="Unknown"):
    """Fetch flights in a specific bounding box"""
    lamin, lamax, lomin, lomax = bbox
    url = (
        "https://opensky-network.org/api/states/all"
        f"?lamin={lamin}&lamax={lamax}&lomin={lomin}&lomax={lomax}"
    )
    
    try:
        res = requests.get(url, timeout=15)
        if res.status_code != 200:
            print(f"   [!] Error fetching {region_name}: HTTP {res.status_code}")
            return pd.DataFrame()
        
        payload = res.json()
        states = payload.get("states", []) or []
        
        if not states:
            return pd.DataFrame()
        
        columns = [
            "icao24", "callsign", "origin_country", "time_position", "last_contact",
            "lon", "lat", "baro_altitude", "on_ground", "velocity", "heading",
            "vertical_rate", "sensors", "geo_altitude", "squawk",
            "spi", "position_source"
        ]
        
        df = pd.DataFrame(states, columns=columns)
        df["timestamp"] = datetime.utcnow()
        df["region"] = region_name
        df["callsign"] = df["callsign"].fillna("").str.strip()
        df["geo_altitude"] = df["geo_altitude"].fillna(df["baro_altitude"])
        
        return df
    
    except Exception as e:
        print(f"   [!] Exception fetching {region_name}: {e}")
        return pd.DataFrame()


def filter_medium_risk_flights(df):
    """Filter for flights in MEDIUM-risk conditions"""
    if df.empty:
        return df
    
    medium_risk_flights = []
    
    # Criterion 1: Moderate descent/climb (5-10 m/s) - not emergency but elevated
    moderate_vertical = df[
        (df['vertical_rate'].abs() >= 5) & 
        (df['vertical_rate'].abs() <= 10)
    ].copy()
    if not moderate_vertical.empty:
        moderate_vertical['risk_reason'] = 'moderate_vertical_rate'
        medium_risk_flights.append(moderate_vertical)
    
    # Criterion 2: Moderately low altitude (2000-5000m) during flight
    moderate_altitude = df[
        (df['baro_altitude'] >= 2000) & 
        (df['baro_altitude'] <= 5000) &
        (df['velocity'] > 60) &  # In flight, not landing
        (df['on_ground'] == False)
    ].copy()
    if not moderate_altitude.empty:
        moderate_altitude['risk_reason'] = 'moderate_low_altitude'
        medium_risk_flights.append(moderate_altitude)
    
    # Criterion 3: Medium speed at low altitude (not extremely fast, but notable)
    moderate_approach = df[
        (df['baro_altitude'] < 3000) & 
        (df['velocity'] >= 60) & 
        (df['velocity'] <= 80) &  # Medium speed range
        (df['on_ground'] == False)
    ].copy()
    if not moderate_approach.empty:
        moderate_approach['risk_reason'] = 'moderate_speed_approach'
        medium_risk_flights.append(moderate_approach)
    
    # Criterion 4: Flights in descent phase (negative vertical rate but not extreme)
    descent_phase = df[
        (df['vertical_rate'] < -2) & 
        (df['vertical_rate'] > -10) &  # Descending but not rapidly
        (df['baro_altitude'] > 1000)
    ].copy()
    if not descent_phase.empty:
        descent_phase['risk_reason'] = 'descent_phase'
        medium_risk_flights.append(descent_phase)
    
    # Criterion 5: Medium altitude cruise (10000-20000m) with any vertical activity
    medium_cruise = df[
        (df['baro_altitude'] >= 10000) & 
        (df['baro_altitude'] <= 20000) &
        (df['vertical_rate'].abs() > 2)  # Some vertical movement
    ].copy()
    if not medium_cruise.empty:
        medium_cruise['risk_reason'] = 'medium_altitude_cruise'
        medium_risk_flights.append(medium_cruise)
    
    if medium_risk_flights:
        result = pd.concat(medium_risk_flights, ignore_index=True)
        # Remove duplicates (a flight can match multiple criteria)
        result = result.drop_duplicates(subset=['icao24', 'timestamp'])
        return result
    
    return pd.DataFrame()


def enrich_with_moderate_weather(df):
    """Add MODERATE weather data to flights using grid-based clustering to reduce API calls
    
    Args:
        df: DataFrame of flights
    """
    if df.empty:
        return df
    
    print(f"   [*] Enriching {len(df)} flights with moderate weather data (grid-based clustering)...")
    
    # Create 1° x 1° grid cells (~111km)
    df['grid_lat'] = (df['lat'] // 1).astype(int)
    df['grid_lon'] = (df['lon'] // 1).astype(int)
    df['grid_cell'] = df['grid_lat'].astype(str) + '_' + df['grid_lon'].astype(str)
    
    # Get unique grid cells
    unique_cells = df.groupby('grid_cell').first()[['lat', 'lon', 'baro_altitude']].reset_index()
    
    print(f"       → {len(df)} flights clustered into {len(unique_cells)} grid cells (1° x 1° = ~111km)")
    
    # Fetch weather for each grid cell (only once per cell)
    weather_cache = {}
    api_success = 0
    api_failures = 0
    consecutive_failures = 0
    max_consecutive_failures = 5  # Switch to simulated weather after 5 consecutive failures
    use_simulated = False
    
    # Moderate weather conditions (fallback templates)
    moderate_conditions = [
        {'condition': 'Rain', 'description': 'light rain', 'wind_base': 12, 'visibility_base': 5000, 'temp_base': 12},
        {'condition': 'Clouds', 'description': 'overcast', 'wind_base': 10, 'visibility_base': 7000, 'temp_base': 10},
        {'condition': 'Fog', 'description': 'foggy', 'wind_base': 5, 'visibility_base': 3000, 'temp_base': 8},
        {'condition': 'Drizzle', 'description': 'light drizzle', 'wind_base': 8, 'visibility_base': 6000, 'temp_base': 15},
        {'condition': 'Mist', 'description': 'misty', 'wind_base': 7, 'visibility_base': 4000, 'temp_base': 11},
    ]
    
    for idx, cell in unique_cells.iterrows():
        grid_id = cell['grid_cell']
        lat, lon = cell['lat'], cell['lon']
        altitude = cell['baro_altitude']
        
        try:
            if weather_service and not use_simulated:
                weather = None
                retries = 2  # Reduced from 3 to 2 attempts
                
                for attempt in range(retries):
                    try:
                        weather = weather_service.get_weather_at_position(lat, lon, altitude)
                        api_success += 1
                        consecutive_failures = 0  # Reset on success
                        # Rate limiting: 60 calls/min = 1 call per second
                        time.sleep(1.2)
                        break  # Success, exit retry loop
                    except Exception as api_error:
                        if attempt < retries - 1:  # Not the last attempt
                            print(f"       ⚠️  Weather API timeout (attempt {attempt+1}/{retries}) - retrying in 10s...")
                            time.sleep(10)  # Reduced from 60 to 10 seconds
                        else:  # Last attempt failed
                            api_failures += 1
                            consecutive_failures += 1
                            
                            # Check if we should switch to simulated weather
                            if consecutive_failures >= max_consecutive_failures:
                                use_simulated = True
                                print(f"       🔄 Too many API failures ({consecutive_failures}), switching to simulated weather for remaining cells")
                            
                            condition_template = moderate_conditions[idx % len(moderate_conditions)]
                            weather = {
                                'temperature': condition_template['temp_base'] + (idx % 10) - 5,
                                'humidity': 70 + (idx % 20),
                                'wind_speed': condition_template['wind_base'] + (idx % 8),
                                'wind_direction': 180 + (idx % 180),
                                'visibility': condition_template['visibility_base'] + (idx % 2000),
                                'cloud_cover': 60 + (idx % 30),
                                'condition': condition_template['condition'],
                                'description': f"{condition_template['description']} (API failed)"
                            }
            else:
                # No weather service or switched to simulated, use moderate defaults with variety
                condition_template = moderate_conditions[idx % len(moderate_conditions)]
                weather = {
                    'temperature': condition_template['temp_base'] + (idx % 10) - 5,
                    'humidity': 70 + (idx % 20),
                    'wind_speed': condition_template['wind_base'] + (idx % 8),
                    'wind_direction': 180 + (idx % 180),
                    'visibility': condition_template['visibility_base'] + (idx % 2000),
                    'cloud_cover': 60 + (idx % 30),
                    'condition': condition_template['condition'],
                    'description': f"{condition_template['description']} (simulated)"
                }
            weather_cache[grid_id] = weather
        except Exception as e:
            # Fallback for any other errors - use moderate conditions
            api_failures += 1
            condition_template = moderate_conditions[0]  # Default to rain
            weather_cache[grid_id] = {
                'temperature': 12,
                'humidity': 75,
                'wind_speed': 12,
                'wind_direction': 270,
                'visibility': 5000,
                'cloud_cover': 70,
                'condition': 'Rain',
                'description': 'moderate weather (error)'
            }
    
    # Assign weather from cache to all flights in each grid cell
    weather_data = []
    for idx, row in df.iterrows():
        grid_id = row['grid_cell']
        weather_data.append(weather_cache[grid_id])
    
    if weather_service:
        print(f"       → Weather API: {api_success} calls (instead of {len(df)}), {api_failures} failures")
        print(f"       → Efficiency: {100 * (1 - api_success/len(df)):.1f}% reduction in API calls")
    else:
        print(f"       → No API key configured, using simulated weather for all {len(df)} flights")
    
    # Remove grid helper columns
    df = df.drop(columns=['grid_lat', 'grid_lon', 'grid_cell'])
    
    weather_df = pd.DataFrame(weather_data)
    result = pd.concat([df.reset_index(drop=True), weather_df], axis=1)
    
    return result


def collect_medium_risk_data(duration_minutes=30, collection_interval=30):
    """
    Collect medium-risk flight data over a period of time.
    
    Args:
        duration_minutes: Total collection duration (default 30 min)
        collection_interval: Seconds between collections (default 30s)
    """
    print("="*60)
    print("MEDIUM-RISK FLIGHT DATA COLLECTOR")
    print("="*60)
    print(f"Duration: {duration_minutes} minutes")
    print(f"Collection interval: {collection_interval} seconds")
    print(f"Target regions: {len(MEDIUM_RISK_REGIONS)}")
    print()
    
    output_dir = Path("real_flight_data")
    output_dir.mkdir(exist_ok=True)
    
    start_time = datetime.now()
    end_time = start_time + timedelta(minutes=duration_minutes)
    
    all_medium_risk_flights = []
    collection_count = 0
    seen_flights = set()  # Track unique flight IDs to avoid duplicates
    
    while datetime.now() < end_time:
        collection_count += 1
        remaining = (end_time - datetime.now()).total_seconds() / 60
        
        print(f"\n[Collection #{collection_count}] - {remaining:.1f} minutes remaining")
        print("-" * 60)
        
        # Collect from all medium-risk regions
        region_data = []
        for region_name, bbox in MEDIUM_RISK_REGIONS.items():
            print(f"   [*] Scanning {region_name}...")
            flights = fetch_flights_bbox(bbox, region_name)
            
            if not flights.empty:
                print(f"       → Found {len(flights)} total flights")
                medium_risk = filter_medium_risk_flights(flights)
                
                if not medium_risk.empty:
                    # Filter out already-seen flights
                    new_flights = medium_risk[~medium_risk['icao24'].isin(seen_flights)]
                    if not new_flights.empty:
                        # Track these flights as seen
                        seen_flights.update(new_flights['icao24'].tolist())
                        print(f"       ✓ {len(new_flights)} NEW medium-risk flights ({len(medium_risk) - len(new_flights)} duplicates skipped)")
                        region_data.append(new_flights)
                    else:
                        print(f"       - All {len(medium_risk)} flights already collected (duplicates)")
                else:
                    print(f"       - No medium-risk flights in this region")
            else:
                print(f"       - No flights found")
            
            # Rate limiting for OpenSky API
            time.sleep(2)
        
        if region_data:
            batch_df = pd.concat(region_data, ignore_index=True)
            
            # Enrich with moderate weather (with robust error handling)
            batch_df = enrich_with_moderate_weather(batch_df)
            
            all_medium_risk_flights.append(batch_df)
            
            print(f"\n   📊 Batch summary: {len(batch_df)} medium-risk flights collected")
            print(f"   📈 Total collected so far: {sum(len(df) for df in all_medium_risk_flights)}")
        
        # Wait before next collection
        if datetime.now() < end_time:
            print(f"\n   ⏳ Waiting {collection_interval} seconds...")
            time.sleep(collection_interval)
    
    # Save results
    if all_medium_risk_flights:
        final_df = pd.concat(all_medium_risk_flights, ignore_index=True)
        
        # Double-check for any remaining duplicates
        initial_count = len(final_df)
        final_df = final_df.drop_duplicates(
            subset=['icao24', 'lat', 'lon', 'baro_altitude'],
            keep='first'
        )
        if len(final_df) < initial_count:
            print(f"\n   ⚠️  Removed {initial_count - len(final_df)} additional duplicates in final cleanup")
        
        # NOTE: We do NOT assign risk_level here!
        # Risk levels will be calculated consistently during training using the
        # heuristic risk_score formula. This ensures experimental consistency.
        # The 'risk_reason' column documents WHY each flight was collected.
        
        # Save to CSV
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = output_dir / f"medium_risk_flights_{timestamp}.csv"
        final_df.to_csv(output_file, index=False)
        
        print("\n" + "="*60)
        print("COLLECTION COMPLETE!")
        print("="*60)
        print(f"✓ Total medium-risk flights collected: {len(final_df)}")
        print(f"✓ Saved to: {output_file}")
        print(f"\n💡 Note: risk_level will be calculated during training for consistency")
        
        # Show risk reasons (WHY collected)
        if 'risk_reason' in final_df.columns:
            print(f"\n🔍 Collection Reasons:")
            reason_counts = final_df['risk_reason'].value_counts()
            for reason, count in reason_counts.items():
                print(f"   {reason}: {count}")
        
        return final_df
    else:
        print("\n❌ No medium-risk flights found during collection period")
        return pd.DataFrame()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Collect medium-risk flight data')
    parser.add_argument('--duration', type=int, default=30,
                       help='Collection duration in minutes (default: 30)')
    parser.add_argument('--interval', type=int, default=30,
                       help='Collection interval in seconds (default: 30)')
    
    args = parser.parse_args()
    
    collect_medium_risk_data(
        duration_minutes=args.duration,
        collection_interval=args.interval
    )

# Usage:
# python collect_medium_risk_data.py --duration 1 --interval 30
