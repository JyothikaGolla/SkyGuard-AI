import pandas as pd
from src.features.build_features import build_featured_flights

df = pd.read_csv('real_flight_data/global_20260108_000331.csv')
if 'baro_altitude' in df.columns:
    df['altitude'] = df['baro_altitude']
if 'time_position' in df.columns:
    df['time'] = df['time_position']

df_feat = build_featured_flights(df)

expected = [
    'temperature', 'wind_speed', 'visibility', 'severe_weather',
    'crosswind', 'headwind', 'low_visibility', 'precipitation',
    'vertical_rate', 'velocity', 'altitude_change_rate',
    'altitude', 'heading', 'speed_kmh',
    'is_climbing', 'is_descending', 'is_turning',
    'altitude_category', 'wind_category', 'time_of_day_category',
    'day_of_week', 'turbulence', 'icing_conditions'
]

print("Expected 21 features for XGBoost:")
for feat in expected:
    status = "✓" if feat in df_feat.columns else "✗ MISSING"
    print(f"  {status} {feat}")

print(f"\nAvailable: {sum(1 for f in expected if f in df_feat.columns)}/21")
print(f"\nMissing features: {[f for f in expected if f not in df_feat.columns]}")