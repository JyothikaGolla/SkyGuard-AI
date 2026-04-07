"""
Trajectory prediction using LSTM for forecasting future flight positions.
"""
import numpy as np
import tensorflow as tf
from tensorflow import keras
from keras import layers
import joblib
import os
from sklearn.preprocessing import StandardScaler


class TrajectoryPredictor:
    def __init__(self, sequence_length=10, forecast_steps=5, n_features=4):
        """
        Initialize trajectory predictor.
        
        Args:
            sequence_length: Number of past timesteps to use
            forecast_steps: Number of future timesteps to predict
            n_features: Number of features (lat, lon, alt, heading)
        """
        self.sequence_length = sequence_length
        self.forecast_steps = forecast_steps
        self.n_features = n_features
        self.model = None
        self.scaler = StandardScaler()  # Add scaler for feature normalization
        
    def build_model(self):
        """Build LSTM model with ENHANCED anti-overfitting for small datasets."""
        model = keras.Sequential([
            # First LSTM layer (REDUCED from 64 to 32 for smaller dataset)
            layers.LSTM(32, activation='relu', return_sequences=True,
                       input_shape=(self.sequence_length, self.n_features),
                       kernel_regularizer=keras.regularizers.l2(0.01),
                       recurrent_regularizer=keras.regularizers.l2(0.01),  # NEW: recurrent regularization
                       recurrent_dropout=0.3),  # INCREASED from 0.2
            layers.BatchNormalization(),  # NEW: Batch normalization for stability
            layers.Dropout(0.5),  # INCREASED from 0.4
            
            # Second LSTM layer (REDUCED from 32 to 16)
            layers.LSTM(16, activation='relu', return_sequences=False,
                       kernel_regularizer=keras.regularizers.l2(0.01),
                       recurrent_regularizer=keras.regularizers.l2(0.01),  # NEW: recurrent regularization
                       recurrent_dropout=0.3),  # INCREASED from 0.2
            layers.BatchNormalization(),  # NEW: Batch normalization for stability
            layers.Dropout(0.5),  # INCREASED from 0.4
            
            # Dense layer (REDUCED from 16 to 8)
            layers.Dense(8, activation='relu',
                        kernel_regularizer=keras.regularizers.l2(0.01)),
            layers.Dropout(0.4),  # INCREASED from 0.3
            
            # Output layer
            layers.Dense(self.forecast_steps * self.n_features),
            layers.Reshape((self.forecast_steps, self.n_features))
        ])
        
        # REDUCED learning rate for better generalization
        optimizer = keras.optimizers.Adam(learning_rate=0.0003)
        model.compile(optimizer=optimizer, loss='mse', metrics=['mae'])
        self.model = model
        return model
    
    def train(self, X, y, epochs=50, batch_size=32, validation_split=0.2):
        """
        Train trajectory predictor.
        
        Args:
            X: Input sequences (n_samples, sequence_length, n_features)
            y: Target sequences (n_samples, forecast_steps, n_features)
            epochs: Training epochs
            batch_size: Batch size
            validation_split: Validation fraction
        """
        if self.model is None:
            self.build_model()
                # Scale features for better convergence
        n_samples, n_timesteps, n_features = X.shape
        X_reshaped = X.reshape(-1, n_features)
        X_scaled = self.scaler.fit_transform(X_reshaped)
        X_train_scaled = X_scaled.reshape(n_samples, n_timesteps, n_features)
        
        # Scale targets
        y_reshaped = y.reshape(-1, n_features)
        y_scaled = self.scaler.transform(y_reshaped)
        y_train_scaled = y_scaled.reshape(n_samples, self.forecast_steps, n_features)
                # Callbacks for better training with ENHANCED early stopping
        early_stopping = keras.callbacks.EarlyStopping(
            monitor='val_loss',
            patience=20,  # INCREASED from 15 for more patience with small dataset
            restore_best_weights=True,
            min_delta=0.001  # INCREASED from 0.0001 for more selective stopping
        )
        
        reduce_lr = keras.callbacks.ReduceLROnPlateau(
            monitor='val_loss',
            factor=0.5,
            patience=7,
            min_lr=0.00001,
            verbose=1
        )
        
        history = self.model.fit(
            X_train_scaled, y_train_scaled,
            epochs=epochs,
            batch_size=batch_size,
            validation_split=validation_split,
            callbacks=[early_stopping, reduce_lr],
            verbose=1
        )
        
        return history
    
    def predict(self, X):
        """
        Predict future trajectory.
        
        Args:
            X: Input sequence (n_samples, sequence_length, n_features)
            
        Returns:
            predictions: Predicted trajectory (n_samples, forecast_steps, n_features)
        """
        if self.model is None:
            raise ValueError("Model not trained. Call train() first.")
        
        return self.model.predict(X, verbose=0)
    
    def save(self, model_path='models/trajectory_predictor.keras'):
        """Save model."""
        os.makedirs(os.path.dirname(model_path), exist_ok=True)
        self.model.save(model_path)
    
    def load(self, model_path='models/trajectory_predictor.keras'):
        """Load model."""
        # Try new format first, then fall back to old format
        if not os.path.exists(model_path) and os.path.exists(model_path.replace('.keras', '.h5')):
            model_path = model_path.replace('.keras', '.h5')
        
        self.model = keras.models.load_model(model_path, compile=False)
        # Recompile with current Keras version
        self.model.compile(optimizer='adam', loss='mse', metrics=['mae'])
        
        self.sequence_length = self.model.input_shape[1]
        self.n_features = self.model.input_shape[2]
        self.forecast_steps = self.model.output_shape[1]


def prepare_trajectory_data(df, sequence_length=10, forecast_steps=5):
    """
    Prepare data for trajectory prediction.
    
    Args:
        df: DataFrame with columns [lat, lon, altitude, heading]
        sequence_length: Input sequence length
        forecast_steps: Output forecast steps
        
    Returns:
        X: Input sequences
        y: Target sequences
    """
    features = df[['lat', 'lon', 'altitude', 'heading']].ffill().values
    
    X, y = [], []
    for i in range(len(features) - sequence_length - forecast_steps + 1):
        X.append(features[i:i + sequence_length])
        y.append(features[i + sequence_length:i + sequence_length + forecast_steps])
    
    return np.array(X), np.array(y)
