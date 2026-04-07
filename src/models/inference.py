"""
Model inference module for real-time predictions.
Loads and manages all ML models for production use.
"""
import numpy as np
import pandas as pd
import os
import logging
from typing import Dict, Optional, Tuple

# Lazy imports to avoid loading heavy models unnecessarily
logger = logging.getLogger(__name__)


class ModelInference:
    """Manages all ML models for real-time inference."""
    
    def __init__(self, models_dir='models'):
        self.models_dir = models_dir
        self.lstm_autoencoder = None
        self.risk_predictor = None
        self.isolation_forest = None
        self.trajectory_predictor = None
        self.clusterer = None
        self.future_risk_predictor = None  # NEW: For future risk prediction
        self.threshold_manager = None      # NEW: For dynamic thresholds
        self._models_loaded = False
        
    def load_models(self):
        """Load all available trained models."""
        logger.info("Loading ML models...")
        
        # Load LSTM Autoencoder
        lstm_path = os.path.join(self.models_dir, 'lstm_autoencoder.keras')
        lstm_path_h5 = os.path.join(self.models_dir, 'lstm_autoencoder.h5')
        lstm_threshold_path = os.path.join(self.models_dir, 'lstm_threshold.pkl')
        
        # Try .keras format first, fall back to .h5
        if (os.path.exists(lstm_path) or os.path.exists(lstm_path_h5)) and os.path.exists(lstm_threshold_path):
            try:
                from src.models.lstm_autoencoder import LSTMAutoencoder
                self.lstm_autoencoder = LSTMAutoencoder()
                self.lstm_autoencoder.load(lstm_path, lstm_threshold_path)
                logger.info("✓ LSTM Autoencoder loaded")
            except Exception as e:
                logger.warning(f"Failed to load LSTM Autoencoder: {e}")
        
        # Load Risk Predictor
        risk_path = os.path.join(self.models_dir, 'risk_predictor.pkl')
        if os.path.exists(risk_path):
            try:
                from src.models.risk_predictor import RiskPredictor
                self.risk_predictor = RiskPredictor()
                self.risk_predictor.load(risk_path)
                logger.info("✓ Risk Predictor loaded")
            except Exception as e:
                logger.warning(f"Failed to load Risk Predictor: {e}")
        
        # Load Isolation Forest
        iso_path = os.path.join(self.models_dir, 'isolation_forest.pkl')
        if os.path.exists(iso_path):
            try:
                from src.models.isolation_forest import FlightIsolationForest
                self.isolation_forest = FlightIsolationForest()
                self.isolation_forest.load(iso_path)
                logger.info("✓ Isolation Forest loaded")
            except Exception as e:
                logger.warning(f"Failed to load Isolation Forest: {e}")
        
        # Load Trajectory Predictor
        traj_path = os.path.join(self.models_dir, 'trajectory_predictor.keras')
        traj_path_h5 = os.path.join(self.models_dir, 'trajectory_predictor.h5')
        
        if os.path.exists(traj_path) or os.path.exists(traj_path_h5):
            try:
                from src.models.trajectory_predictor import TrajectoryPredictor
                self.trajectory_predictor = TrajectoryPredictor()
                self.trajectory_predictor.load(traj_path)
                logger.info("✓ Trajectory Predictor loaded")
            except Exception as e:
                logger.warning(f"Failed to load Trajectory Predictor: {e}")
        
        # Load Clusterer
        cluster_path = os.path.join(self.models_dir, 'flight_clusterer.pkl')
        if os.path.exists(cluster_path):
            try:
                from src.models.clustering import FlightClusterer
                self.clusterer = FlightClusterer()
                self.clusterer.load(cluster_path)
                logger.info("✓ Flight Clusterer loaded")
            except Exception as e:
                logger.warning(f"Failed to load Flight Clusterer: {e}")
        
        # Load Dynamic Threshold Manager (NEW)
        try:
            from src.config.risk_thresholds import get_threshold_manager
            self.threshold_manager = get_threshold_manager()
            logger.info("✓ Dynamic Threshold Manager initialized")
        except ImportError as e:
            logger.warning(f"Threshold Manager not available: {e}")
        
        # Initialize Future Risk Predictor (NEW)
        try:
            from src.models.future_risk_predictor import FutureRiskPredictor
            self.future_risk_predictor = FutureRiskPredictor(
                trajectory_predictor=self.trajectory_predictor,
                risk_predictor=self.risk_predictor,
                threshold_manager=self.threshold_manager
            )
            logger.info("✓ Future Risk Predictor initialized")
        except ImportError as e:
            logger.warning(f"Future Risk Predictor not available: {e}")
        
        self._models_loaded = True
        logger.info("Model loading complete")
    
    def predict_risk(self, features: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        Predict risk using XGBoost model.
        
        Args:
            features: Feature matrix
            
        Returns:
            risk_scores: Continuous risk scores (0-1)
            risk_levels: Risk level labels (0=LOW, 1=MEDIUM, 2=HIGH)
        """
        if self.risk_predictor is None:
            # Fallback to heuristic if model not loaded
            return None, None
        
        try:
            risk_levels, risk_probs = self.risk_predictor.predict(features)
            risk_scores = self.risk_predictor.get_risk_score(features)
            return risk_scores, risk_levels
        except Exception as e:
            logger.error(f"Risk prediction failed: {e}")
            return None, None
    
    def detect_anomalies_lstm(self, sequences: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        Detect anomalies using LSTM Autoencoder.
        
        Args:
            sequences: Time series sequences (n_samples, sequence_length, n_features)
            
        Returns:
            anomaly_scores: Anomaly scores (0-1)
            is_anomaly: Boolean array
        """
        if self.lstm_autoencoder is None:
            return None, None
        
        try:
            return self.lstm_autoencoder.detect_anomaly(sequences)
        except Exception as e:
            logger.error(f"LSTM anomaly detection failed: {e}")
            return None, None
    
    def detect_anomalies_isolation(self, features: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        Detect anomalies using Isolation Forest.
        
        Args:
            features: Feature matrix
            
        Returns:
            is_outlier: Boolean array
            outlier_scores: Outlier scores (0-1)
        """
        if self.isolation_forest is None:
            return None, None
        
        try:
            return self.isolation_forest.predict_outliers(features)
        except Exception as e:
            logger.error(f"Isolation Forest anomaly detection failed: {e}")
            return None, None
    
    def predict_trajectory(self, sequences: np.ndarray) -> Optional[np.ndarray]:
        """
        Predict future trajectory.
        
        Args:
            sequences: Historical sequences (n_samples, sequence_length, n_features)
            
        Returns:
            predictions: Future trajectory predictions
        """
        if self.trajectory_predictor is None:
            return None
        
        try:
            return self.trajectory_predictor.predict(sequences)
        except Exception as e:
            logger.error(f"Trajectory prediction failed: {e}")
            return None
    
    def predict_cluster(self, features: np.ndarray) -> Optional[np.ndarray]:
        """
        Predict flight cluster.
        
        Args:
            features: Feature matrix
            
        Returns:
            cluster_labels: Cluster assignments
        """
        if self.clusterer is None:
            return None
        
        try:
            return self.clusterer.predict(features)
        except Exception as e:
            logger.error(f"Clustering prediction failed: {e}")
            return None
    
    def get_cluster_distance(self, features: np.ndarray) -> Optional[np.ndarray]:
        """
        Get distance to nearest cluster center.
        
        Args:
            features: Feature matrix
            
        Returns:
            distances: Distance to nearest cluster
        """
        if self.clusterer is None or self.clusterer.method != 'kmeans':
            return None
        
        try:
            return self.clusterer.get_cluster_distances(features)
        except Exception as e:
            logger.error(f"Cluster distance calculation failed: {e}")
            return None
    
    def predict_future_risk(self,
                           current_sequence: np.ndarray,
                           current_features: np.ndarray,
                           time_horizon: int = 5,
                           time_step_seconds: int = 60) -> Optional[Dict]:
        """
        Predict risk evolution over time (NEW FEATURE - Professor Requirement #3).
        
        Args:
            current_sequence: Recent trajectory (sequence_length, 4)
            current_features: Current flight features
            time_horizon: Number of future timesteps
            time_step_seconds: Seconds between timesteps
        
        Returns:
            Dictionary with future risk predictions
        """
        if self.future_risk_predictor is None:
            logger.warning("Future risk predictor not available")
            return None
        
        try:
            return self.future_risk_predictor.predict_future_risk(
                current_sequence, current_features,
                time_horizon, time_step_seconds
            )
        except Exception as e:
            logger.error(f"Future risk prediction failed: {e}")
            return None
    
    def predict_risk_at_distance(self,
                                current_sequence: np.ndarray,
                                current_features: np.ndarray,
                                distance_km: float,
                                average_speed_kmh: float = 800) -> Optional[Dict]:
        """
        Predict risk after traveling a certain distance (NEW FEATURE).
        
        Args:
            current_sequence: Recent trajectory
            current_features: Current flight features
            distance_km: Distance to travel
            average_speed_kmh: Average speed
        
        Returns:
            Dictionary with future risk predictions
        """
        if self.future_risk_predictor is None:
            logger.warning("Future risk predictor not available")
            return None
        
        try:
            return self.future_risk_predictor.predict_risk_at_distance(
                current_sequence, current_features,
                distance_km, average_speed_kmh
            )
        except Exception as e:
            logger.error(f"Risk at distance prediction failed: {e}")
            return None
    
    def get_dynamic_thresholds(self,
                              altitude: float = None,
                              flight_phase: str = None,
                              weather_condition: str = None) -> Optional[Tuple[float, float]]:
        """
        Get dynamic risk thresholds based on context (NEW FEATURE - Professor Requirement #1).
        
        Args:
            altitude: Current altitude
            flight_phase: Flight phase
            weather_condition: Weather condition
        
        Returns:
            (low_threshold, high_threshold) tuple
        """
        if self.threshold_manager is None:
            logger.warning("Threshold manager not available")
            return (0.33, 0.66)  # Default fixed thresholds
        
        try:
            return self.threshold_manager.get_thresholds(
                altitude, flight_phase, weather_condition
            )
        except Exception as e:
            logger.error(f"Dynamic threshold calculation failed: {e}")
            return (0.33, 0.66)  # Fallback to defaults
    
    def classify_risk_dynamic(self,
                             risk_score: float,
                             altitude: float = None,
                             flight_phase: str = None,
                             weather_condition: str = None) -> str:
        """
        Classify risk using dynamic thresholds (NEW FEATURE).
        
        Args:
            risk_score: Continuous risk score
            altitude: Current altitude
            flight_phase: Flight phase
            weather_condition: Weather condition
        
        Returns:
            'LOW', 'MEDIUM', or 'HIGH'
        """
        if self.threshold_manager is None:
            # Fallback to fixed thresholds
            if risk_score < 0.33:
                return 'LOW'
            elif risk_score < 0.66:
                return 'MEDIUM'
            else:
                return 'HIGH'
        
        try:
            return self.threshold_manager.classify_risk(
                risk_score, altitude, flight_phase, weather_condition
            )
        except Exception as e:
            logger.error(f"Dynamic risk classification failed: {e}")
            # Fallback to fixed thresholds
            if risk_score < 0.33:
                return 'LOW'
            elif risk_score < 0.66:
                return 'MEDIUM'
            else:
                return 'HIGH'


# Global model instance (singleton pattern)
_model_instance = None


def get_model_instance(models_dir='models'):
    """Get or create global model instance."""
    global _model_instance
    if _model_instance is None:
        _model_instance = ModelInference(models_dir)
        # Try to load models on first access
        try:
            _model_instance.load_models()
        except Exception as e:
            logger.warning(f"Could not load models on initialization: {e}")
    return _model_instance
