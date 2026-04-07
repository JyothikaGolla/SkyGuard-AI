"""
Quick script to check if weather data is integrated and varying.
"""
import pandas as pd
import os
from pathlib import Path

def check_weather_integration():
    """Check if weather data is present and varying in collected data."""
    
    data_dir = Path('real_flight_data')
    
    # Find all CSV files
    csv_files = list(data_dir.glob('global_*.csv')) + list(data_dir.glob('high_risk_*.csv'))
    
    if not csv_files:
        print("❌ No data files found in real_flight_data/")
        return
    
    # Check the most recent file
    latest_file = max(csv_files, key=lambda x: x.stat().st_mtime)
    
    print(f"=" * 70)
    print(f"WEATHER DATA INTEGRATION CHECK")
    print(f"=" * 70)
    print(f"\n📁 Checking: {latest_file.name}")
    print(f"📅 Last Modified: {pd.Timestamp.fromtimestamp(latest_file.stat().st_mtime)}")
    
    # Load the data
    df = pd.read_csv(latest_file)
    
    print(f"\n📊 Total Records: {len(df)}")
    print(f"📋 Total Columns: {len(df.columns)}")
    
    # Check for weather columns
    weather_columns = [
        'temperature', 'pressure', 'humidity', 'wind_speed', 'wind_direction',
        'visibility', 'cloud_cover', 'condition', 'description',
        'weather_risk_score', 'severe_weather', 'low_visibility', 
        'high_winds', 'icing_risk'
    ]
    
    present_weather_cols = [col for col in weather_columns if col in df.columns]
    missing_weather_cols = [col for col in weather_columns if col not in df.columns]
    
    print(f"\n🌤️  Weather Columns Present: {len(present_weather_cols)}/{len(weather_columns)}")
    
    if not present_weather_cols:
        print("\n❌ NO WEATHER DATA FOUND!")
        print("   The API key might not be configured correctly.")
        return
    
    print(f"   ✅ Found: {', '.join(present_weather_cols)}")
    if missing_weather_cols:
        print(f"   ⚠️  Missing: {', '.join(missing_weather_cols)}")
    
    # Check if weather data is varying (not constant)
    print(f"\n{'=' * 70}")
    print("WEATHER DATA STATISTICS")
    print(f"{'=' * 70}")
    
    for col in ['temperature', 'wind_speed', 'visibility', 'severe_weather', 
                'low_visibility', 'high_winds']:
        if col in df.columns:
            min_val = df[col].min()
            max_val = df[col].max()
            unique_count = df[col].nunique()
            mean_val = df[col].mean()
            
            # Check if constant
            is_constant = (min_val == max_val)
            
            if col in ['severe_weather', 'low_visibility', 'high_winds']:
                # Boolean columns
                status = "🔴 CONSTANT" if is_constant else "✅ VARYING"
                true_count = int(df[col].sum())
                false_count = int((df[col] == 0).sum())
                print(f"{col:20s}: {status:15s} | True: {true_count}, False: {false_count}")
            else:
                # Numeric columns
                status = "🔴 CONSTANT" if is_constant else "✅ VARYING"
                print(f"{col:20s}: {status:15s} | Range: [{min_val:.2f}, {max_val:.2f}] | Unique: {unique_count}")
    
    # Check weather conditions variety
    if 'condition' in df.columns:
        print(f"\n{'=' * 70}")
        print("WEATHER CONDITIONS DIVERSITY")
        print(f"{'=' * 70}")
        conditions = df['condition'].value_counts()
        print(f"Unique conditions: {len(conditions)}")
        print("\nTop conditions:")
        for condition, count in conditions.head(10).items():
            percentage = (count / len(df)) * 100
            print(f"  {condition:20s}: {count:6d} ({percentage:5.2f}%)")
    
    # Overall assessment
    print(f"\n{'=' * 70}")
    print("ASSESSMENT")
    print(f"{'=' * 70}")
    
    # Check key weather columns
    key_cols = ['temperature', 'wind_speed', 'visibility']
    varying_count = sum(1 for col in key_cols if col in df.columns and df[col].nunique() > 1)
    
    if varying_count == len(key_cols):
        print("✅ SUCCESS: Weather API is working and data is varying!")
        print("   Your model will learn weather-risk correlations.")
    elif varying_count > 0:
        print("⚠️  PARTIAL: Some weather data is varying, but not all.")
        print(f"   {varying_count}/{len(key_cols)} key columns have variation.")
    else:
        print("❌ FAILED: Weather data is constant (using defaults).")
        print("   Check your API key configuration.")
    
    print(f"\n{'=' * 70}")

if __name__ == '__main__':
    check_weather_integration()
