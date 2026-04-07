"""
Specialized data collector for HIGH-RISK flight scenarios.
Targets flights likely to be in dangerous conditions:
- Severe weather areas (thunderstorms, high winds)
- Rapid altitude changes (emergency descents)
- Low altitude high-speed approaches
- Extreme weather regions
- Known turbulence zones
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


# High-risk flight regions (known for severe weather, mountain turbulence, etc.)
HIGH_RISK_REGIONS = {
    'north_atlantic_storms': (40, 60, -50, -10),  # North Atlantic storm corridor
    'himalayas': (25, 35, 75, 95),                 # Himalayan mountain turbulence
    'florida_hurricanes': (24, 31, -88, -79),      # Florida hurricane zone
    'rocky_mountains': (37, 49, -115, -100),       # Rocky Mountain turbulence
    'european_alps': (43, 48, 5, 15),              # Alps turbulence zone
    'pacific_typhoons': (20, 35, 120, 145),        # Western Pacific typhoon belt
    'andes_mountains': (-35, -15, -75, -65),       # Andes turbulence
    'midwest_tornadoes': (30, 42, -105, -85),      # US Tornado Alley
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


def filter_high_risk_flights(df):
    """Filter for flights in high-risk conditions"""
    if df.empty:
        return df
    
    high_risk_flights = []
    
    # Criterion 1: Rapid descent (potential emergency)
    rapid_descent = df[df['vertical_rate'] < -10].copy()  # > 10 m/s descent
    if not rapid_descent.empty:
        rapid_descent['risk_reason'] = 'rapid_descent'
        high_risk_flights.append(rapid_descent)
    
    # Criterion 2: Low altitude + high speed (risky approach)
    low_alt_high_speed = df[
        (df['baro_altitude'] < 1500) & 
        (df['velocity'] > 80) & 
        (df['on_ground'] == False)
    ].copy()
    if not low_alt_high_speed.empty:
        low_alt_high_speed['risk_reason'] = 'low_altitude_high_speed'
        high_risk_flights.append(low_alt_high_speed)
    
    # Criterion 3: Extreme altitude changes
    if 'vertical_rate' in df.columns:
        extreme_vertical = df[abs(df['vertical_rate']) > 15].copy()  # Very high climb/descent
        if not extreme_vertical.empty:
            extreme_vertical['risk_reason'] = 'extreme_vertical_rate'
            high_risk_flights.append(extreme_vertical)
    
    # Criterion 4: Emergency squawk codes
    if 'squawk' in df.columns:
        emergency_squawks = df[df['squawk'].isin(['7500', '7600', '7700'])].copy()
        if not emergency_squawks.empty:
            emergency_squawks['risk_reason'] = 'emergency_squawk'
            high_risk_flights.append(emergency_squawks)
    
    # Criterion 5: Unusual altitude for cruise (too low or erratic)
    cruise_flights = df[
        (df['baro_altitude'] > 500) & 
        (df['baro_altitude'] < 15000) &  # Between 500-15000m is unusual cruise
        (df['velocity'] > 50)
    ].copy()
    if not cruise_flights.empty:
        cruise_flights['risk_reason'] = 'unusual_altitude'
        high_risk_flights.append(cruise_flights)
    
    if high_risk_flights:
        result = pd.concat(high_risk_flights, ignore_index=True)
        # Remove duplicates (a flight can match multiple criteria)
        result = result.drop_duplicates(subset=['icao24', 'timestamp'])
        return result
    
    return pd.DataFrame()


def enrich_with_weather(df):
    """Add weather data to flights using grid-based clustering to reduce API calls
    
    Args:
        df: DataFrame of flights
    """
    if df.empty:
        return df
    
    print(f"   [*] Enriching {len(df)} flights with weather data (grid-based clustering)...")
    
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
                            
                            weather = {
                                'temperature': -20 + (idx % 20),
                                'humidity': 85,
                                'wind_speed': 25 + (idx % 10),
                                'wind_direction': 270,
                                'visibility': 2000 + (idx % 1000),
                                'cloud_cover': 90,
                                'condition': 'Thunderstorm',
                                'description': 'severe weather (API failed)'
                            }
            else:
                # No weather service or switched to simulated, use high-risk defaults
                weather = {
                    'temperature': -20 + (idx % 20),
                    'humidity': 85,
                    'wind_speed': 25 + (idx % 10),
                    'wind_direction': 270,
                    'visibility': 2000 + (idx % 1000),
                    'cloud_cover': 90,
                    'condition': 'Thunderstorm',
                    'description': 'severe weather (simulated)'
                }
            weather_cache[grid_id] = weather
        except Exception as e:
            # Fallback for any other errors
            api_failures += 1
            weather_cache[grid_id] = {
                'temperature': -20,
                'humidity': 85,
                'wind_speed': 25,
                'wind_direction': 270,
                'visibility': 2000,
                'cloud_cover': 90,
                'condition': 'Thunderstorm',
                'description': 'severe weather (error)'
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


def collect_high_risk_data(duration_minutes=30, collection_interval=30):
    """
    Collect high-risk flight data over a period of time.
    
    Args:
        duration_minutes: Total collection duration (default 30 min)
        collection_interval: Seconds between collections (default 30s)
    """
    print("="*60)
    print("HIGH-RISK FLIGHT DATA COLLECTOR")
    print("="*60)
    print(f"Duration: {duration_minutes} minutes")
    print(f"Collection interval: {collection_interval} seconds")
    print(f"Target regions: {len(HIGH_RISK_REGIONS)}")
    print()
    
    output_dir = Path("real_flight_data")
    output_dir.mkdir(exist_ok=True)
    
    start_time = datetime.now()
    end_time = start_time + timedelta(minutes=duration_minutes)
    
    all_high_risk_flights = []
    collection_count = 0
    seen_flights = set()  # Track unique flight IDs to avoid duplicates
    
    while datetime.now() < end_time:
        collection_count += 1
        remaining = (end_time - datetime.now()).total_seconds() / 60
        
        print(f"\n[Collection #{collection_count}] - {remaining:.1f} minutes remaining")
        print("-" * 60)
        
        # Collect from all high-risk regions
        region_data = []
        for region_name, bbox in HIGH_RISK_REGIONS.items():
            print(f"   [*] Scanning {region_name}...")
            flights = fetch_flights_bbox(bbox, region_name)
            
            if not flights.empty:
                print(f"       → Found {len(flights)} total flights")
                high_risk = filter_high_risk_flights(flights)
                
                if not high_risk.empty:
                    # Filter out already-seen flights
                    new_flights = high_risk[~high_risk['icao24'].isin(seen_flights)]
                    if not new_flights.empty:
                        # Track these flights as seen
                        seen_flights.update(new_flights['icao24'].tolist())
                        print(f"       ✓ {len(new_flights)} NEW high-risk flights ({len(high_risk) - len(new_flights)} duplicates skipped)")
                        region_data.append(new_flights)
                    else:
                        print(f"       - All {len(high_risk)} flights already collected (duplicates)")
                else:
                    print(f"       - No high-risk flights in this region")
            else:
                print(f"       - No flights found")
            
            # Rate limiting for OpenSky API
            time.sleep(2)
        
        if region_data:
            batch_df = pd.concat(region_data, ignore_index=True)
            
            # Enrich with weather (with robust error handling)
            batch_df = enrich_with_weather(batch_df)
            
            all_high_risk_flights.append(batch_df)
            
            print(f"\n   📊 Batch summary: {len(batch_df)} high-risk flights collected")
            print(f"   📈 Total collected so far: {sum(len(df) for df in all_high_risk_flights)}")
        
        # Wait before next collection
        if datetime.now() < end_time:
            print(f"\n   ⏳ Waiting {collection_interval} seconds...")
            time.sleep(collection_interval)
    
    # Save results
    if all_high_risk_flights:
        final_df = pd.concat(all_high_risk_flights, ignore_index=True)
        
        # Double-check for any remaining duplicates (shouldn't be any after real-time filtering)
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
        output_file = output_dir / f"high_risk_flights_{timestamp}.csv"
        final_df.to_csv(output_file, index=False)
        
        print("\n" + "="*60)
        print("COLLECTION COMPLETE!")
        print("="*60)
        print(f"✓ Total high-risk flights collected: {len(final_df)}")
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
        print("\n❌ No high-risk flights found during collection period")
        return pd.DataFrame()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Collect high-risk flight data')
    parser.add_argument('--duration', type=int, default=30,
                       help='Collection duration in minutes (default: 30)')
    parser.add_argument('--interval', type=int, default=30,
                       help='Collection interval in seconds (default: 30)')
    
    args = parser.parse_args()
    
    collect_high_risk_data(
        duration_minutes=args.duration,
        collection_interval=args.interval
    )

# .\venv\Scripts\python.exe collect_high_risk_data.py --duration 1 --interval 30