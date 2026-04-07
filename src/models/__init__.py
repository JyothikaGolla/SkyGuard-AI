"""
Machine Learning Models for Flight Risk AI

This package contains advanced ML models for:
- Risk prediction (XGBoost)
- Anomaly detection (LSTM Autoencoder, Isolation Forest)
- Trajectory forecasting (LSTM)
- Flight pattern clustering (K-Means)
"""

__version__ = "1.0.0"

from .risk_predictor import RiskPredictor
from .lstm_autoencoder import LSTMAutoencoder
from .isolation_forest import FlightIsolationForest
from .trajectory_predictor import TrajectoryPredictor
from .clustering import FlightClusterer
from .inference import ModelInference, get_model_instance

__all__ = [
    'RiskPredictor',
    'LSTMAutoencoder',
    'FlightIsolationForest',
    'TrajectoryPredictor',
    'FlightClusterer',
    'ModelInference',
    'get_model_instance'
]
