import pandas as pd
import numpy as np
from scipy.stats import zscore
from datetime import datetime
import math


def add_basic_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add basic flight features."""
    df = df.copy()

    # Speed in km/h (velocity is m/s)
    df["speed_kmh"] = df["velocity"].fillna(0) * 3.6

    # Flags for climbing / descending based on vertical rate
    df["is_climbing"] = (df["vertical_rate"] > 1).astype(int)
    df["is_descending"] = (df["vertical_rate"] < -1).astype(int)

    # Replace NaNs in altitude
    if 'geo_altitude' in df.columns and 'baro_altitude' in df.columns:
        df["altitude"] = df["geo_altitude"].fillna(df["baro_altitude"]).fillna(0)
    elif 'geo_altitude' in df.columns:
        df["altitude"] = df["geo_altitude"].fillna(0)
    elif 'baro_altitude' in df.columns:
        df["altitude"] = df["baro_altitude"].fillna(0)
    elif 'altitude' not in df.columns:
        df["altitude"] = 0

    # Simple altitude bins
    df["altitude_bin"] = pd.cut(df["altitude"], bins=[-100, 1000, 5000, 10000, 20000, 50000],
                                labels=False, include_lowest=True).fillna(0).astype(int)

    return df


def add_advanced_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add advanced ML-ready features for flight analysis.
    
    Features include:
    - Velocity and acceleration metrics
    - Altitude change patterns
    - Heading variations
    - Temporal features
    - Statistical aggregations
    """
    df = df.copy()
    
    # Sort by ICAO24 and time for sequential calculations
    df = df.sort_values(['icao24', 'last_contact'])
    
    # === Time-based features ===
    df['time_since_last_update'] = df.groupby('icao24')['last_contact'].diff().fillna(0)
    
    # === Velocity and acceleration ===
    df['speed_variation'] = df.groupby('icao24')['velocity'].transform(
        lambda x: x.rolling(window=3, min_periods=1).std()
    ).fillna(0)
    
    df['acceleration'] = df.groupby('icao24')['velocity'].diff().fillna(0) / \
                        df['time_since_last_update'].replace(0, 1)
    df['acceleration'] = df['acceleration'].clip(-100, 100)  # Expanded: allow extreme G-forces
    
    # === Altitude metrics ===
    df['altitude_change_rate'] = df.groupby('icao24')['altitude'].diff().fillna(0) / \
                                df['time_since_last_update'].replace(0, 1)
    df['altitude_change_rate'] = df['altitude_change_rate'].clip(-150, 150)  # Expanded: allow freefall/emergency
    
    df['altitude_std'] = df.groupby('icao24')['altitude'].transform(
        lambda x: x.rolling(window=5, min_periods=1).std()
    ).fillna(0)
    
    # === Heading and direction ===
    df['heading_change'] = df.groupby('icao24')['heading'].diff().fillna(0)
    # Handle circular nature of heading (0-360 degrees)
    df['heading_change'] = df['heading_change'].apply(
        lambda x: x - 360 if x > 180 else (x + 360 if x < -180 else x)
    )
    
    df['heading_change_rate'] = df['heading_change'] / df['time_since_last_update'].replace(0, 1)
    df['heading_change_rate'] = df['heading_change_rate'].clip(-360, 360)  # Expanded: allow rapid spins
    
    # === Vertical rate features ===
    df['vertical_rate_abs'] = df['vertical_rate'].abs()
    df['vertical_rate_change'] = df.groupby('icao24')['vertical_rate'].diff().fillna(0)
    
    # === Position-based features ===
    df['lat_change'] = df.groupby('icao24')['lat'].diff().fillna(0)
    df['lon_change'] = df.groupby('icao24')['lon'].diff().fillna(0)
    
    # Approximate distance traveled (simplified haversine)
    df['distance_traveled'] = np.sqrt(
        (df['lat_change'] * 111)**2 + 
        (df['lon_change'] * 111 * np.cos(np.radians(df['lat'])))**2
    )  # km
    
    # === Speed categories ===
    df['speed_category'] = pd.cut(
        df['speed_kmh'], 
        bins=[0, 200, 500, 800, 1200],
        labels=['slow', 'medium', 'fast', 'very_fast']
    ).astype(str).replace('nan', 'unknown')
    
    # === Flight phase estimation ===
    def estimate_flight_phase(row):
        """Estimate flight phase based on altitude and vertical rate."""
        alt = row['altitude']
        vr = row['vertical_rate']
        
        if alt < 1000:
            if vr > 2:
                return 'takeoff'
            elif vr < -2:
                return 'landing'
            return 'ground'
        elif alt < 3000:
            if vr > 5:
                return 'climb'
            elif vr < -5:
                return 'descent'
            return 'low_cruise'
        else:
            if vr > 3:
                return 'climb'
            elif vr < -3:
                return 'descent'
            return 'cruise'
    
    df['flight_phase'] = df.apply(estimate_flight_phase, axis=1)
    
    # === Statistical features ===
    # Z-scores for outlier detection (with epsilon to prevent division by zero)
    numeric_cols = ['velocity', 'altitude', 'vertical_rate']
    for col in numeric_cols:
        if col in df.columns:
            def safe_zscore(x):
                if len(x) <= 1:
                    return 0
                std = x.std()
                if std < 1e-6:  # Check if std is effectively zero
                    return 0
                return (x - x.mean()) / std
            
            df[f'{col}_zscore'] = df.groupby('icao24')[col].transform(safe_zscore).fillna(0)
    
    # === Rolling statistics ===
    df['velocity_ma_5'] = df.groupby('icao24')['velocity'].transform(
        lambda x: x.rolling(window=5, min_periods=1).mean()
    ).fillna(df['velocity'])
    
    df['altitude_ma_5'] = df.groupby('icao24')['altitude'].transform(
        lambda x: x.rolling(window=5, min_periods=1).mean()
    ).fillna(df['altitude'])
    
    # === Boolean flags ===
    df['is_stationary'] = ((df['velocity'] < 1) & (df['on_ground'] == True)).astype(int)
    df['is_high_altitude'] = (df['altitude'] > 10000).astype(int)
    df['is_rapid_descent'] = (df['vertical_rate'] < -10).astype(int)
    df['is_rapid_climb'] = (df['vertical_rate'] > 10).astype(int)
    df['is_sharp_turn'] = (df['heading_change_rate'].abs() > 10).astype(int)
    
    return df


def add_weather_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add weather-based features from weather data.
    
    Expects df to have either:
    1. 'weather' column (dict) with weather fields, OR
    2. Individual weather columns already extracted (from CSV files)
    
    Weather features:
    - temperature, pressure, humidity
    - wind_speed, wind_direction
    - visibility, cloud_cover
    - weather_risk_score
    - severe_weather, low_visibility, high_winds, icing_risk
    """
    df = df.copy()
    
    # Check if weather columns already exist (e.g., from CSV files)
    weather_cols = ['temperature', 'wind_speed', 'visibility']
    has_weather_cols = all(col in df.columns for col in weather_cols)
    
    # If weather data already exists as columns, just ensure all fields are present
    if has_weather_cols:
        # Weather columns already extracted from CSV - fill in any missing ones
        if 'pressure' not in df.columns:
            df['pressure'] = 1013
        if 'humidity' not in df.columns:
            df['humidity'] = 50
        if 'wind_direction' not in df.columns:
            df['wind_direction'] = 0
        if 'cloud_cover' not in df.columns:
            df['cloud_cover'] = 0
        if 'weather_risk_score' not in df.columns:
            df['weather_risk_score'] = 0
        if 'severe_weather' not in df.columns:
            df['severe_weather'] = 0
        if 'low_visibility' not in df.columns:
            df['low_visibility'] = 0
        if 'high_winds' not in df.columns:
            df['high_winds'] = 0
        if 'icing_risk' not in df.columns:
            df['icing_risk'] = 0
        # Skip to wind component calculation (don't overwrite existing data!)
    elif 'weather' not in df.columns:
        # No weather data at all - use defaults
        df['temperature'] = 15
        df['pressure'] = 1013
        df['humidity'] = 50
        df['wind_speed'] = 0
        df['wind_direction'] = 0
        df['visibility'] = 10000
        df['cloud_cover'] = 0
        df['weather_risk_score'] = 0
        df['severe_weather'] = 0
        df['low_visibility'] = 0
        df['high_winds'] = 0
        df['icing_risk'] = 0
        df['crosswind'] = 0
        df['headwind'] = 0
        return df
    else:
        # Extract weather dict fields (for real-time API data)
        df['temperature'] = df['weather'].apply(lambda x: x.get('temperature', 15) if isinstance(x, dict) else 15)
        df['pressure'] = df['weather'].apply(lambda x: x.get('pressure', 1013) if isinstance(x, dict) else 1013)
        df['humidity'] = df['weather'].apply(lambda x: x.get('humidity', 50) if isinstance(x, dict) else 50)
        df['wind_speed'] = df['weather'].apply(lambda x: x.get('wind_speed', 0) if isinstance(x, dict) else 0)
        df['wind_direction'] = df['weather'].apply(lambda x: x.get('wind_direction', 0) if isinstance(x, dict) else 0)
        df['visibility'] = df['weather'].apply(lambda x: x.get('visibility', 10000) if isinstance(x, dict) else 10000)
        df['cloud_cover'] = df['weather'].apply(lambda x: x.get('cloud_cover', 0) if isinstance(x, dict) else 0)
        df['weather_risk_score'] = df['weather'].apply(lambda x: x.get('weather_risk_score', 0) if isinstance(x, dict) else 0)
        
        # Boolean weather flags
        df['severe_weather'] = df['weather'].apply(lambda x: int(x.get('severe_weather', False)) if isinstance(x, dict) else 0)
        df['low_visibility'] = df['weather'].apply(lambda x: int(x.get('low_visibility', False)) if isinstance(x, dict) else 0)
        df['high_winds'] = df['weather'].apply(lambda x: int(x.get('high_winds', False)) if isinstance(x, dict) else 0)
        df['icing_risk'] = df['weather'].apply(lambda x: int(x.get('icing_risk', False)) if isinstance(x, dict) else 0)
    
    # Calculate crosswind and headwind components
    def calculate_wind_components(row):
        """Calculate crosswind and headwind relative to aircraft heading."""
        if pd.isna(row['heading']) or pd.isna(row['wind_direction']) or pd.isna(row['wind_speed']):
            return 0, 0
        
        # Angle between wind and heading
        angle_diff = abs(row['wind_direction'] - row['heading'])
        if angle_diff > 180:
            angle_diff = 360 - angle_diff
        
        # Crosswind (perpendicular component)
        crosswind = row['wind_speed'] * abs(math.sin(math.radians(angle_diff)))
        
        # Headwind (parallel component, negative = tailwind)
        headwind = row['wind_speed'] * math.cos(math.radians(angle_diff))
        
        return crosswind, headwind
    
    # Apply wind component calculations
    wind_components = df.apply(calculate_wind_components, axis=1, result_type='expand')
    df['crosswind'] = wind_components[0]
    df['headwind'] = wind_components[1]
    
    # Derived weather risk features
    df['visibility_risk'] = (10000 - df['visibility'].clip(0, 10000)) / 10000  # 0-1 scale
    df['wind_risk'] = df['wind_speed'].clip(0, 30) / 30  # 0-1 scale
    df['temp_extreme'] = df['temperature'].apply(lambda x: 1 if x < -20 or x > 45 else 0)
    
    # Combined weather hazard score
    df['weather_hazard'] = (
        df['severe_weather'] * 0.4 +
        df['low_visibility'] * 0.25 +
        df['high_winds'] * 0.2 +
        df['icing_risk'] * 0.15
    ).clip(0, 1)
    
    return df


def add_heuristic_risk(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add enhanced risk/anomaly scores combining heuristics and ML-ready features.
    Now includes weather-based risk factors AND extreme condition detection.
    
    This provides fallback risk scoring when ML models are not available,
    but uses more sophisticated heuristics than before.
    """
    df = df.copy()

    # Normalize some values roughly (expanded ranges for extreme scenarios)
    alt = df["altitude"].clip(lower=-200, upper=25000) / 25000.0  # Include below sea level + stratosphere
    speed = df["speed_kmh"].clip(lower=0, upper=1500) / 1500.0  # Include hypersonic
    v_rate = df["vertical_rate"].fillna(0).clip(-100, 100) / 100.0  # Include freefall/emergency
    
    # === Enhanced risk scoring ===
    risk = 0.0
    
    # 1. Low altitude high speed risk
    risk += (1 - alt) * 0.25 * speed
    
    # 2. Rapid descent near ground
    risk += (df["is_descending"] * (1 - alt) * 0.2)
    
    # 3. Rapid altitude changes (expanded)
    if 'altitude_change_rate' in df.columns:
        alt_change_norm = df['altitude_change_rate'].abs().clip(0, 150) / 150  # Match expanded limit
        risk += alt_change_norm * 0.1
    
    # 4. Sharp turns (expanded)
    if 'heading_change_rate' in df.columns:
        turn_norm = df['heading_change_rate'].abs().clip(0, 360) / 360  # Match expanded limit
        risk += turn_norm * 0.08
    
    # 5. High acceleration/deceleration (expanded)
    if 'acceleration' in df.columns:
        accel_norm = df['acceleration'].abs().clip(0, 100) / 100  # Match expanded limit
        risk += accel_norm * 0.07
    
    # 6. Unstable vertical rate (expanded)
    if 'vertical_rate_change' in df.columns:
        vr_change_norm = df['vertical_rate_change'].abs().clip(0, 50) / 50  # Allow more variation
        risk += vr_change_norm * 0.08
    
    # === EXTREME CONDITION DETECTION (from high-risk collection criteria) ===
    # These are CRITICAL high-risk indicators that should push risk to HIGH
    
    # 7. Rapid descent (> 10 m/s down) - EMERGENCY INDICATOR
    if 'vertical_rate' in df.columns:
        rapid_descent = (df['vertical_rate'] < -10).astype(float)
        risk += rapid_descent * 0.4  # Strong penalty
    
    # 8. Extreme vertical rate (> 15 m/s either direction) - VERY DANGEROUS
    if 'vertical_rate' in df.columns:
        extreme_vr = (df['vertical_rate'].abs() > 15).astype(float)
        risk += extreme_vr * 0.45  # Very strong penalty
    
    # 9. Low altitude + high speed combination (< 1500m AND > 80 m/s)
    low_alt_high_speed = ((df['altitude'] < 1500) & (df['velocity'] > 80)).astype(float)
    risk += low_alt_high_speed * 0.35  # Strong penalty
    
    # 10. Unusual cruise altitude (500-15000m is risky for cruise)
    unusual_alt = ((df['altitude'] > 500) & (df['altitude'] < 15000) & (df['velocity'] > 50)).astype(float)
    risk += unusual_alt * 0.15  # Moderate penalty
    
    # === WEATHER RISK INTEGRATION ===
    # 11. Weather risk score (normalized 0-1)
    if 'weather_risk_score' in df.columns:
        weather_risk_norm = df['weather_risk_score'].clip(0, 100) / 100
        risk += weather_risk_norm * 0.15
    
    # 12. Crosswind at low altitude
    if 'crosswind' in df.columns:
        crosswind_risk = (df['crosswind'].clip(0, 20) / 20) * (1 - alt)
        risk += crosswind_risk * 0.1
    
    # 13. Low visibility combined with low altitude
    if 'low_visibility' in df.columns:
        visibility_alt_risk = df['low_visibility'] * (1 - alt) * 0.12
        risk += visibility_alt_risk
    
    # 14. Severe weather penalty
    if 'severe_weather' in df.columns:
        risk += df['severe_weather'] * 0.2
    
    # 15. Icing conditions
    if 'icing_risk' in df.columns:
        risk += df['icing_risk'] * 0.1
    
    # Clamp between 0 and 1
    df["risk_score"] = risk.clip(0, 1)

    # === Enhanced anomaly scoring ===
    anomaly = 0.0
    
    # 1. Extreme vertical rates
    anomaly += np.abs(v_rate) * 0.3
    
    # 2. Unusual speeds
    anomaly += (speed - 0.7).clip(lower=0) * 0.2
    
    # 3. Z-score based anomalies
    if 'velocity_zscore' in df.columns:
        anomaly += df['velocity_zscore'].abs().clip(0, 3) / 3 * 0.2
    
    if 'altitude_zscore' in df.columns:
        anomaly += df['altitude_zscore'].abs().clip(0, 3) / 3 * 0.15
    
    if 'vertical_rate_zscore' in df.columns:
        anomaly += df['vertical_rate_zscore'].abs().clip(0, 3) / 3 * 0.15
    
    df["anomaly_score"] = anomaly.clip(0, 1)

    # Risk level buckets
    def bucket(x):
        if x < 0.33:
            return "LOW"
        elif x < 0.66:
            return "MEDIUM"
        return "HIGH"

    # ALWAYS recalculate risk_level from risk_score for consistency
    # This ensures the same risk logic is applied to all data (synthetic & real)
    df["risk_level"] = df["risk_score"].apply(bucket)
    
    # Add anomaly level
    df["anomaly_level"] = df["anomaly_score"].apply(bucket)
    
    return df


def apply_dynamic_thresholds(df: pd.DataFrame, threshold_manager=None) -> pd.DataFrame:
    """
    Apply dynamic risk thresholds based on flight context (NEW FEATURE).
    
    This recalculates risk_level using variable thresholds instead of fixed 0.33/0.66.
    Addresses Professor Requirement #1: Variable thresholds based on context.
    
    Args:
        df: DataFrame with risk_score, altitude, flight_phase, weather columns
        threshold_manager: Optional RiskThresholdManager instance
    
    Returns:
        DataFrame with updated risk_level column
    """
    if threshold_manager is None:
        # Use default fixed thresholds if manager not provided
        return df
    
    df = df.copy()
    
    # Extract context columns
    altitudes = df['altitude'].values if 'altitude' in df.columns else None
    phases = df['flight_phase'].values if 'flight_phase' in df.columns else None
    
    # Extract weather conditions
    weather_conditions = None
    if 'weather' in df.columns:
        # Extract condition from weather dict/JSON
        def extract_condition(w):
            if isinstance(w, dict):
                return w.get('condition', 'clear')
            elif isinstance(w, str):
                import json
                try:
                    wd = json.loads(w)
                    return wd.get('condition', 'clear')
                except:
                    return 'clear'
            return 'clear'
        weather_conditions = df['weather'].apply(extract_condition).values
    
    # Apply dynamic classification
    risk_levels = threshold_manager.classify_risk_batch(
        df['risk_score'].values,
        altitudes=altitudes,
        flight_phases=phases,
        weather_conditions=weather_conditions
    )
    
    df['risk_level'] = risk_levels
    df['dynamic_thresholds_applied'] = True
    
    return df


def build_featured_flights(df_raw, use_dynamic_thresholds=False, threshold_manager=None):
    """
    Complete feature engineering pipeline with weather integration.
    
    Args:
        df_raw: Raw flight data from OpenSky (optionally with 'weather' column)
        use_dynamic_thresholds: If True, apply dynamic context-based thresholds (NEW)
        threshold_manager: Optional RiskThresholdManager instance (NEW)
        
    Returns:
        DataFrame with all features including weather, risk scores, and anomaly scores
    """
    df = add_basic_features(df_raw)
    df = add_advanced_features(df)
    df = add_weather_features(df)  # Add weather features
    df = add_heuristic_risk(df)
    
    # Apply dynamic thresholds if requested (NEW FEATURE)
    if use_dynamic_thresholds:
        if threshold_manager is None:
            # Import and create default manager
            try:
                from src.config.risk_thresholds import get_threshold_manager
                threshold_manager = get_threshold_manager()
            except ImportError:
                pass  # Fall back to fixed thresholds
        
        if threshold_manager is not None:
            df = apply_dynamic_thresholds(df, threshold_manager)
    
    return df
