"""
Real Flight Data Collection Script

Fetches real flight data from OpenSky Network API with rate limiting.
Saves data to CSV files for later training use.

Usage:
    python collect_real_data.py --requests 10 --region india
"""
import argparse
import time
import pandas as pd
from datetime import datetime
import os
from src.data.fetch_opensky import fetch_flights
from src.data.fetch_weather import WeatherService
from config import OPENWEATHER_API_KEY

# Region bounding boxes
REGIONS = {
    'india': (6, 38, 68, 98),
    'usa_east': (25, 50, -100, -65),
    'usa_west': (30, 50, -125, -100),
    'europe': (35, 70, -15, 40),
    'china': (20, 50, 70, 135),
    'japan': (30, 45, 125, 150),
    'australia': (-45, -10, 110, 160),
    'south_america': (-55, 12, -82, -34),
    'middle_east': (12, 42, 25, 65),
    'africa': (-35, 37, -18, 52),
}

# Global collection (no bbox - gets worldwide data)
GLOBAL_MODE = None

def collect_flight_batch(bbox=None, delay=30):
    """
    Collect one batch of flights with weather data.
    
    Args:
        bbox: Bounding box (min_lat, max_lat, min_lon, max_lon) or None for global
        delay: Seconds to wait before next request (default 30)
    
    Returns:
        DataFrame with flight and weather data
    """
    if bbox is None:
        print(f"\n⏳ Fetching flights globally (no region restriction)...")
    else:
        print(f"\n⏳ Fetching flights for bbox {bbox}...")
    
    try:
        flights_df = fetch_flights(bbox) if bbox else fetch_flights()
        
        if flights_df.empty:
            print("❌ No flights found in this region")
            return pd.DataFrame()
        
        print(f"✅ Fetched {len(flights_df)} flights")
        
        # Add weather data using WeatherService
        print("🌤️  Fetching weather data...")
        weather_service = WeatherService(api_key=OPENWEATHER_API_KEY)
        
        # Get weather for all flights
        result_df = weather_service.get_weather_for_flights(flights_df)
        
        # Extract weather dict into separate columns
        if 'weather' in result_df.columns:
            weather_cols = pd.json_normalize(result_df['weather'])
            result_df = pd.concat([result_df.drop('weather', axis=1), weather_cols], axis=1)
        
        print(f"✅ Added weather data for {len(result_df)} flights")
        
        return result_df
        
    except Exception as e:
        print(f"❌ Error fetching flights: {e}")
        import traceback
        traceback.print_exc()
        return pd.DataFrame()


def save_batch(df, region_name):
    """Save batch to CSV file with timestamp."""
    if df.empty:
        return None
    
    # Create data directory
    data_dir = "real_flight_data"
    os.makedirs(data_dir, exist_ok=True)
    
    # Generate filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{data_dir}/{region_name}_{timestamp}.csv"
    
    # Save to CSV
    df.to_csv(filename, index=False)
    print(f"💾 Saved {len(df)} flights to {filename}")
    
    return filename


def load_all_real_data():
    """Load all previously collected real flight data."""
    data_dir = "real_flight_data"
    
    if not os.path.exists(data_dir):
        return pd.DataFrame()
    
    csv_files = [f for f in os.listdir(data_dir) if f.endswith('.csv')]
    
    if not csv_files:
        return pd.DataFrame()
    
    print(f"\n📂 Loading {len(csv_files)} existing data files...")
    
    all_data = []
    for csv_file in csv_files:
        filepath = os.path.join(data_dir, csv_file)
        try:
            df = pd.read_csv(filepath)
            all_data.append(df)
        except Exception as e:
            print(f"⚠️  Error loading {csv_file}: {e}")
    
    if all_data:
        combined = pd.concat(all_data, ignore_index=True)
        print(f"✅ Loaded {len(combined)} total real flight records")
        return combined
    
    return pd.DataFrame()


def main():
    parser = argparse.ArgumentParser(description='Collect real flight data from OpenSky API')
    parser.add_argument('--requests', type=int, default=5,
                       help='Number of API requests to make (default: 5)')
    parser.add_argument('--region', type=str, default=None,
                       choices=list(REGIONS.keys()) + ['all'],
                       help='Region to fetch data from. Use "all" for all regions or omit for global (default: global)')
    parser.add_argument('--delay', type=int, default=30,
                       help='Seconds to wait between requests (default: 30)')
    parser.add_argument('--global', dest='use_global', action='store_true',
                       help='Collect global data (no region restriction)')
    
    args = parser.parse_args()
    
    # Determine collection mode
    if args.use_global or args.region is None:
        regions_to_collect = ['global']
        bbox_list = [None]  # None means no bbox restriction
        print("\n🌍 GLOBAL MODE: Collecting worldwide flight data")
    elif args.region == 'all':
        regions_to_collect = list(REGIONS.keys())
        bbox_list = [REGIONS[r] for r in regions_to_collect]
        print(f"\n🌎 ALL REGIONS MODE: Collecting from {len(regions_to_collect)} regions")
    else:
        regions_to_collect = [args.region]
        bbox_list = [REGIONS[args.region]]
    
    print("="*60)
    print("🛩️  REAL FLIGHT DATA COLLECTION")
    print("="*60)
    
    if len(regions_to_collect) == 1 and bbox_list[0] is not None:
        print(f"\nRegion: {regions_to_collect[0].upper()}")
        print(f"Bounding box: {bbox_list[0]}")
    elif len(regions_to_collect) > 1:
        print(f"\nRegions: {', '.join([r.upper() for r in regions_to_collect])}")
    
    print(f"Requests per region: {args.requests}")
    print(f"Delay between requests: {args.delay}s")
    total_requests = args.requests * len(regions_to_collect)
    print(f"\n⏱️  Estimated time: {total_requests * args.delay / 60:.1f} minutes")
    print(f"\n⚠️  Note: OpenSky API has ~100 requests/hour limit")
    print(f"         Be patient and respect rate limits!\n")
    
    # Load existing data
    existing_data = load_all_real_data()
    if not existing_data.empty:
        print(f"📊 Current dataset: {len(existing_data)} flights")
    
    # Collect new batches
    all_batches = []
    successful_requests = 0
    total_flights = 0
    
    # Iterate through regions
    for region_idx, (region_name, bbox) in enumerate(zip(regions_to_collect, bbox_list)):
        print(f"\n{'='*60}")
        print(f"🌍 REGION: {region_name.upper()} ({region_idx+1}/{len(regions_to_collect)})")
        print(f"{'='*60}")
        
        # Collect multiple batches for this region
        for i in range(args.requests):
            print(f"\n📡 Request {i+1}/{args.requests} for {region_name}")
            
            # Fetch batch
            batch_df = collect_flight_batch(bbox, args.delay)
            
            if not batch_df.empty:
                # Save immediately
                filename = save_batch(batch_df, region_name)
                if filename:
                    all_batches.append(batch_df)
                    successful_requests += 1
                    total_flights += len(batch_df)
            
            # Wait before next request (except for last one)
            if not (region_idx == len(regions_to_collect) - 1 and i == args.requests - 1):
                print(f"\n⏳ Waiting {args.delay} seconds before next request...")
                time.sleep(args.delay)
    
    # Summary
    print("\n" + "="*60)
    print("📊 COLLECTION SUMMARY")
    print("="*60)
    print(f"✅ Successful requests: {successful_requests}/{total_requests}")
    print(f"📥 New flights collected: {total_flights}")
    
    if len(regions_to_collect) > 1:
        print(f"🌍 Regions covered: {len(regions_to_collect)}")
    
    # Reload all data
    final_data = load_all_real_data()
    if not final_data.empty:
        print(f"📊 Total dataset size: {len(final_data)} flights")
        print(f"🗺️  Unique aircraft: {final_data['icao24'].nunique()}")
        print(f"\n💡 Use these files for training with --use-real-data flag")
        print(f"   Example: python train_models.py --use-real-data")
    else:
        print("❌ No data collected")
    
    print("="*60)


if __name__ == "__main__":
    main()
