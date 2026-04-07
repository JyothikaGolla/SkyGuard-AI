# Flight Risk AI Models

This directory contains trained ML models for flight risk assessment and anomaly detection.

## Models

1. **risk_predictor.pkl** - XGBoost model for risk classification
2. **lstm_autoencoder.h5** - LSTM autoencoder for anomaly detection
3. **isolation_forest.pkl** - Isolation Forest for outlier detection
4. **flight_clusterer.pkl** - K-Means clustering for flight patterns
5. **trajectory_predictor.h5** - LSTM model for trajectory forecasting

## Training

To train all models, run:

```bash
python train_models.py
```

This will generate synthetic training data and train all models.

## Model Details

### Risk Predictor (XGBoost)
- **Input**: 24 features (13 flight dynamics + 11 weather)
- **Output**: Risk level (LOW, MEDIUM, HIGH)
- **Use Case**: Real-time weather-aware risk assessment

### LSTM Autoencoder
- **Input**: Sequences of 10 timesteps × 8 features
- **Output**: Anomaly scores
- **Use Case**: Detecting unusual flight patterns

### Isolation Forest
- **Input**: 13 flight features
- **Output**: Outlier detection
- **Use Case**: Identifying abnormal flights

### Flight Clusterer
- **Input**: 13 flight features (with PCA)
- **Output**: Cluster labels
- **Use Case**: Flight pattern categorization

### Trajectory Predictor
- **Input**: Historical sequences (lat, lon, alt, heading)
- **Output**: Future trajectory predictions
- **Use Case**: Forecasting flight paths
