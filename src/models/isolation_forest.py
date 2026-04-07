"""
Isolation Forest for detecting outlier flights.
Complements LSTM autoencoder with different anomaly detection approach.
"""
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
import joblib
import os


class FlightIsolationForest:
    def __init__(self, contamination=0.1, random_state=42):
        """
        Initialize Isolation Forest for flight outlier detection.
        
        Args:
            contamination: Expected proportion of outliers (0.0 to 0.5)
            random_state: Random seed
        """
        self.model = IsolationForest(
            n_estimators=100,
            contamination=contamination,
            random_state=random_state,
            n_jobs=-1
        )
        self.scaler = StandardScaler()
        self.contamination = contamination
        
    def fit(self, X):
        """
        Fit the Isolation Forest on flight data.
        
        Args:
            X: Feature matrix of shape (n_samples, n_features)
        """
        X_scaled = self.scaler.fit_transform(X)
        self.model.fit(X_scaled)
        
    def predict_outliers(self, X):
        """
        Predict outliers in flight data.
        
        Args:
            X: Feature matrix
            
        Returns:
            is_outlier: Boolean array (True = outlier)
            outlier_scores: Anomaly scores (higher = more anomalous)
        """
        X_scaled = self.scaler.transform(X)
        
        # -1 for outliers, 1 for inliers
        predictions = self.model.predict(X_scaled)
        is_outlier = predictions == -1
        
        # Decision function: lower scores = more anomalous
        decision_scores = self.model.decision_function(X_scaled)
        
        # Normalize to 0-1 (higher = more anomalous)
        outlier_scores = 1 / (1 + np.exp(decision_scores))  # Sigmoid transformation
        
        return is_outlier, outlier_scores
    
    def save(self, model_path='models/isolation_forest.pkl'):
        """Save model and scaler."""
        os.makedirs(os.path.dirname(model_path), exist_ok=True)
        joblib.dump({
            'model': self.model,
            'scaler': self.scaler,
            'contamination': self.contamination
        }, model_path)
    
    def load(self, model_path='models/isolation_forest.pkl'):
        """Load model and scaler."""
        data = joblib.load(model_path)
        self.model = data['model']
        self.scaler = data['scaler']
        self.contamination = data.get('contamination', 0.1)
