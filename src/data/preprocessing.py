"""
Data cleaning and preprocessing utilities for flight data.
"""
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from imblearn.over_sampling import SMOTE
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def clean_flight_data(df):
    """
    Clean and validate flight data.
    
    Removes:
    - Invalid altitude values (negative or unrealistic)
    - Invalid velocity values (negative or supersonic)
    - Invalid coordinates (outside valid ranges)
    - Duplicate records
    - Rows with excessive missing values
    
    Args:
        df: Raw flight DataFrame
        
    Returns:
        Cleaned DataFrame
    """
    initial_count = len(df)
    logger.info(f"Starting data cleaning. Initial records: {initial_count}")
    
    # 1. Remove records with invalid altitudes (expanded limits for extreme cases)
    # -9999 is a common sentinel value in OpenSky data
    df = df[df['altitude'] > -9999]  # Remove only sentinel/error values
    df = df[df['altitude'] < 25000]  # Include U-2, research aircraft (max ~21,000m)
    logger.info(f"After altitude validation: {len(df)} records")
    
    # 2. Remove invalid velocities (expanded for extreme cases)
    df = df[df['velocity'] >= 0]
    df = df[df['velocity'] < 400]  # Include hypersonic research aircraft
    logger.info(f"After velocity validation: {len(df)} records")
    
    # 3. Validate coordinates
    df = df[(df['lat'].notna()) & (df['lon'].notna())]
    df = df[(df['lat'] >= -90) & (df['lat'] <= 90)]
    df = df[(df['lon'] >= -180) & (df['lon'] <= 180)]
    logger.info(f"After coordinate validation: {len(df)} records")
    
    # 4. Expanded vertical rate limits to capture extreme emergency scenarios
    if 'vertical_rate' in df.columns:
        df = df[(df['vertical_rate'].isna()) | 
                ((df['vertical_rate'] >= -100) & (df['vertical_rate'] <= 100))]
    logger.info(f"After vertical rate validation: {len(df)} records")
    
    # 5. Remove duplicates based on flight ID and timestamp
    if 'icao24' in df.columns and 'timestamp' in df.columns:
        df = df.drop_duplicates(subset=['icao24', 'timestamp'], keep='first')
    logger.info(f"After duplicate removal: {len(df)} records")
    
    # 6. Remove rows with too many missing values in CRITICAL columns only
    # Check only essential columns, not all columns
    critical_cols = ['icao24', 'lat', 'lon', 'altitude', 'velocity']
    available_critical = [col for col in critical_cols if col in df.columns]
    
    if available_critical:
        # Only require critical columns to be non-null
        df = df.dropna(subset=available_critical)
    logger.info(f"After missing value removal: {len(df)} records")
    
    removed_count = initial_count - len(df)
    removal_pct = (removed_count / initial_count) * 100
    logger.info(f"Data cleaning complete. Removed {removed_count} records ({removal_pct:.2f}%)")
    
    return df


def detect_and_remove_outliers(df, features, contamination=0.05):
    """
    Detect and remove statistical outliers using IQR method.
    
    Args:
        df: DataFrame
        features: List of feature columns to check
        contamination: Fraction of outliers to remove (default 5%)
        
    Returns:
        DataFrame with outliers removed
    """
    logger.info("Detecting statistical outliers...")
    initial_count = len(df)
    
    for feature in features:
        if feature in df.columns and df[feature].notna().sum() > 0:
            Q1 = df[feature].quantile(0.25)
            Q3 = df[feature].quantile(0.75)
            IQR = Q3 - Q1
            
            # Define outlier bounds
            lower_bound = Q1 - 3 * IQR  # 3x IQR for extreme outliers only
            upper_bound = Q3 + 3 * IQR
            
            # Remove outliers
            df = df[(df[feature] >= lower_bound) & (df[feature] <= upper_bound)]
    
    removed_count = initial_count - len(df)
    logger.info(f"Removed {removed_count} statistical outliers")
    
    return df


def balance_classes(X, y, strategy='auto'):
    """
    Balance class distribution using SMOTE (Synthetic Minority Over-sampling).
    
    Args:
        X: Feature matrix
        y: Target labels
        strategy: Sampling strategy ('auto', 'minority', or dict)
        
    Returns:
        X_balanced, y_balanced
    """
    logger.info("Balancing class distribution with SMOTE...")
    
    # Count original distribution
    unique, counts = np.unique(y, return_counts=True)
    logger.info(f"Original class distribution: {dict(zip(unique, counts))}")
    
    # Find minimum class count
    min_samples = min(counts)
    
    # Adjust k_neighbors based on minimum class size
    # SMOTE requires k_neighbors < min_samples
    k_neighbors = min(5, max(1, min_samples - 1))
    
    if min_samples < 6:
        logger.warning(f"Minority class has only {min_samples} samples. Using k_neighbors={k_neighbors}")
    
    # Apply SMOTE with adjusted k_neighbors
    smote = SMOTE(sampling_strategy=strategy, random_state=42, k_neighbors=k_neighbors)
    X_balanced, y_balanced = smote.fit_resample(X, y)
    
    # Count new distribution
    unique, counts = np.unique(y_balanced, return_counts=True)
    logger.info(f"Balanced class distribution: {dict(zip(unique, counts))}")
    
    return X_balanced, y_balanced


def get_class_weights(y):
    """
    Calculate class weights for imbalanced learning.
    Gives higher weight to minority classes (especially HIGH risk).
    
    Args:
        y: Target labels
        
    Returns:
        Dictionary of class weights
    """
    unique, counts = np.unique(y, return_counts=True)
    total = len(y)
    
    # Compute balanced weights
    weights = {}
    for cls, count in zip(unique, counts):
        # Weight is inversely proportional to frequency
        # Plus extra penalty for HIGH risk class (class 2)
        base_weight = total / (len(unique) * count)
        if cls == 2:  # HIGH risk
            base_weight *= 3  # Triple weight for high risk
        elif cls == 1:  # MEDIUM risk
            base_weight *= 1.5  # 1.5x weight for medium risk
        weights[int(cls)] = base_weight
    
    logger.info(f"Computed class weights: {weights}")
    return weights


def validate_features(X, feature_names):
    """
    Validate feature matrix for common issues.
    
    Args:
        X: Feature matrix
        feature_names: List of feature names
        
    Returns:
        Boolean indicating if features are valid
    """
    logger.info("Validating features...")
    
    # Ensure X is numeric (convert if needed)
    try:
        X = np.asarray(X, dtype=np.float64)
    except (ValueError, TypeError) as e:
        logger.error(f"Could not convert features to numeric: {e}")
        return False
    
    # Check for NaN or Inf values
    if np.isnan(X).any():
        logger.warning("Found NaN values in features!")
        return False
    
    if np.isinf(X).any():
        logger.warning("Found Inf values in features!")
        return False
    
    # Check for constant features (zero variance)
    variances = np.var(X, axis=0)
    constant_features = [feature_names[i] for i, var in enumerate(variances) if var == 0]
    if constant_features:
        logger.warning(f"Found constant features (zero variance): {constant_features}")
    
    # Check feature ranges
    logger.info(f"Feature ranges:")
    for i, name in enumerate(feature_names):
        min_val, max_val = np.min(X[:, i]), np.max(X[:, i])
        logger.info(f"  {name}: [{min_val:.2f}, {max_val:.2f}]")
    
    logger.info("Feature validation complete")
    return True


def prepare_production_data(df):
    """
    Prepare real OpenSky data for production use.
    Applies all cleaning, validation, and preprocessing steps.
    
    Args:
        df: Raw flight DataFrame from OpenSky API
        
    Returns:
        Cleaned and validated DataFrame
    """
    # Apply comprehensive cleaning
    df = clean_flight_data(df)
    
    # Detect outliers in key features
    outlier_features = ['altitude', 'velocity', 'vertical_rate']
    df = detect_and_remove_outliers(df, outlier_features)
    
    return df


def remove_constant_features(df, feature_columns, threshold=0.01):
    """
    Remove features with zero or near-zero variance.
    Useful for removing features that have constant values across all samples.
    
    Args:
        df: DataFrame with features
        feature_columns: List of feature column names to check
        threshold: Minimum variance threshold (default: 0.01)
        
    Returns:
        df: DataFrame with constant features removed
        kept_features: List of non-constant features that were kept
    """
    constant_features = []
    kept_features = []
    
    for col in feature_columns:
        if col in df.columns:
            variance = df[col].var()
            if variance < threshold:
                constant_features.append(col)
            else:
                kept_features.append(col)
    
    if constant_features:
        logger.warning(f"Removing {len(constant_features)} constant/near-constant features (variance < {threshold}): {constant_features}")
        df = df.drop(columns=constant_features)
    else:
        logger.info("No constant features detected - all features have sufficient variance")
    
    return df, kept_features
