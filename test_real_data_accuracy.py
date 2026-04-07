"""
Test the trained model's accuracy on REAL flight data only.
This reveals if high accuracy is legitimate or due to synthetic data overfitting.
"""
import numpy as np
import pandas as pd
import joblib
from pathlib import Path
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score

def load_real_data():
    """Load only real flight data (no synthetic samples)"""
    data_dir = Path('real_flight_data')
    
    if not data_dir.exists():
        raise FileNotFoundError("No real_flight_data directory found")
    
    csv_files = list(data_dir.glob('*.csv'))
    
    if not csv_files:
        raise FileNotFoundError("No real flight data CSV files found in real_flight_data/")
    
    print(f"[*] Loading {len(csv_files)} real flight data files...")
    dfs = []
    for file in csv_files:
        df = pd.read_csv(file)
        # Normalize column names
        if 'baro_altitude' in df.columns and 'altitude' not in df.columns:
            df['altitude'] = df['baro_altitude']
        dfs.append(df)
    
    real_df = pd.concat(dfs, ignore_index=True)
    # Mark as real data
    real_df['origin_country'] = 'Real'
    print(f"[+] Loaded {len(real_df)} real flight records")
    return real_df

def preprocess_real_data(df):
    """Apply the same preprocessing as training pipeline"""
    from src.data.preprocessing import clean_flight_data
    from src.utils.train_models import prepare_ml_features
    
    print("[*] Cleaning and engineering features...")
    cleaned = clean_flight_data(df)
    
    # Use the same feature preparation as training
    X, y, featured = prepare_ml_features(cleaned)
    
    # Use same feature set as training
    feature_cols = [
        'altitude', 'velocity', 'vertical_rate', 'heading',
        'speed_kmh', 'is_climbing', 'is_descending',
        'speed_variation', 'altitude_change_rate', 'heading_change_rate',
        'acceleration',
        'temperature', 'wind_speed', 'visibility',
        'crosswind', 'headwind', 'severe_weather', 'low_visibility',
        'high_winds', 'icing_risk', 'time_since_last_update'
    ]
    
    available_cols = [col for col in feature_cols if col in featured.columns]
    X = featured[available_cols].fillna(0).values
    
    risk_map = {'LOW': 0, 'MEDIUM': 1, 'HIGH': 2}
    y = featured['risk_level'].map(risk_map).values
    
    # Remove invalid labels
    valid_mask = ~np.isnan(y)
    X = X[valid_mask]
    y = y[valid_mask].astype(int)
    
    print(f"[+] Preprocessed {len(X)} valid real flight samples")
    return X, y, available_cols

def test_on_real_data():
    """Test trained model on real data only"""
    print("="*60)
    print("TESTING MODEL ON REAL FLIGHT DATA ONLY")
    print("="*60)
    
    # Load model
    try:
        model_data = joblib.load('models/risk_predictor.pkl')
        
        # Check if it's a RiskPredictor object or dict
        if isinstance(model_data, dict):
            # It's saved as dict with model and scaler separate
            from src.models.risk_predictor import RiskPredictor
            model = RiskPredictor()
            model.model = model_data['model']
            model.scaler = model_data['scaler']
            model.feature_names = model_data.get('feature_names', [])
        else:
            # It's a RiskPredictor object
            model = model_data
        
        print("[+] Loaded trained model from models/risk_predictor.pkl")
    except FileNotFoundError:
        print("❌ ERROR: No trained model found. Run train_models.py first.")
        return
    
    # Load real data
    try:
        real_df = load_real_data()
    except FileNotFoundError as e:
        print(f"❌ ERROR: {e}")
        return
    
    # Preprocess
    X_real, y_real, feature_names = preprocess_real_data(real_df)
    
    # Get predictions
    print("\n[*] Making predictions on real data...")
    X_real_scaled = model.scaler.transform(X_real)
    y_pred = model.model.predict(X_real_scaled)
    
    # Calculate metrics
    accuracy = accuracy_score(y_real, y_pred)
    
    print("\n" + "="*60)
    print("RESULTS: REAL DATA ONLY")
    print("="*60)
    print(f"\n📊 Test Samples: {len(X_real)} (100% real flight data)")
    print(f"🎯 Accuracy on Real Data: {accuracy:.2%}")
    
    # Class distribution
    unique, counts = np.unique(y_real, return_counts=True)
    print("\n📈 Real Data Distribution:")
    for cls, count in zip(unique, counts):
        cls_name = ['LOW', 'MEDIUM', 'HIGH'][cls]
        print(f"   {cls_name}: {count} ({count/len(y_real)*100:.1f}%)")
    
    # Classification report
    print("\n📋 Classification Report:")
    print(classification_report(y_real, y_pred, 
                                target_names=['LOW', 'MEDIUM', 'HIGH'],
                                digits=3))
    
    # Confusion matrix
    cm = confusion_matrix(y_real, y_pred)
    print("\n🔢 Confusion Matrix:")
    print("              Predicted")
    print("              LOW   MED   HIGH")
    for i, row in enumerate(cm):
        cls_name = ['LOW', 'MED', 'HIGH'][i]
        print(f"Actual {cls_name:4s}  {row[0]:5d} {row[1]:5d} {row[2]:5d}")
    
    # Comparison warning
    print("\n" + "="*60)
    print("⚠️  INTERPRETATION:")
    print("="*60)
    if accuracy >= 0.95:
        print("✓ High accuracy on real data suggests model learned")
        print("  genuine flight risk patterns (not just synthetic rules)")
    elif accuracy >= 0.85:
        print("⚠️ Moderate accuracy suggests some overfitting to synthetic data")
        print(f"  Mixed training accuracy: ~99.7%")
        print(f"  Real data accuracy: {accuracy:.1%}")
        print(f"  → Model partially learned synthetic patterns")
    else:
        print("❌ Low accuracy on real data indicates SEVERE overfitting!")
        print(f"  Mixed training accuracy: ~99.7%")
        print(f"  Real data accuracy: {accuracy:.1%}")
        print("  → Model learned synthetic generation rules, not flight risks")
        print("\n  RECOMMENDATION: Train on REAL DATA ONLY or improve synthetic")
        print("  data generation to better match real flight patterns")
    
    return accuracy

if __name__ == "__main__":
    test_on_real_data()
