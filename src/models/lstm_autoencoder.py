"""
LSTM Autoencoder for flight anomaly detection.
Trained on normal flight patterns to identify anomalies.
"""
import numpy as np
import tensorflow as tf
from tensorflow import keras
from keras import layers
import joblib
import os
from sklearn.preprocessing import StandardScaler

class LSTMAutoencoder:
    def __init__(self, sequence_length=10, n_features=8, encoding_dim=16):
        self.sequence_length = sequence_length
        self.n_features = n_features
        self.encoding_dim = encoding_dim
        self.model = None
        self.threshold = None
        self.scaler = StandardScaler()  # Add scaler for feature normalization
        
    def build_model(self):
        """Build LSTM autoencoder architecture with ENHANCED anti-overfitting regularization."""
        # Encoder (reduced capacity to prevent memorization)
        encoder_inputs = layers.Input(shape=(self.sequence_length, self.n_features))
        encoder = layers.LSTM(32, activation='relu', return_sequences=True,
                            kernel_regularizer=keras.regularizers.l2(0.01),  # INCREASED from 0.001
                            recurrent_dropout=0.2)(encoder_inputs)  # NEW: recurrent dropout
        encoder = layers.Dropout(0.4)(encoder)  # INCREASED from 0.3
        encoder = layers.LSTM(16, activation='relu', return_sequences=False,
                            kernel_regularizer=keras.regularizers.l2(0.01),  # INCREASED from 0.001
                            recurrent_dropout=0.2)(encoder)  # NEW: recurrent dropout
        encoder = layers.Dropout(0.3)(encoder)  # INCREASED from 0.2
        
        # Decoder (reduced capacity)
        decoder = layers.RepeatVector(self.sequence_length)(encoder)
        decoder = layers.LSTM(16, activation='relu', return_sequences=True,
                            kernel_regularizer=keras.regularizers.l2(0.01),  # INCREASED from 0.001
                            recurrent_dropout=0.2)(decoder)  # NEW: recurrent dropout
        decoder = layers.Dropout(0.4)(decoder)  # INCREASED from 0.3
        decoder = layers.LSTM(32, activation='relu', return_sequences=True,
                            kernel_regularizer=keras.regularizers.l2(0.01),  # INCREASED from 0.001
                            recurrent_dropout=0.2)(decoder)  # NEW: recurrent dropout
        decoder = layers.Dropout(0.3)(decoder)  # INCREASED from 0.2
        decoder_outputs = layers.TimeDistributed(layers.Dense(self.n_features))(decoder)
        
        # Autoencoder model with reduced learning rate
        optimizer = keras.optimizers.Adam(learning_rate=0.0005)  # REDUCED from 0.001
        self.model = keras.Model(encoder_inputs, decoder_outputs)
        self.model.compile(optimizer=optimizer, loss='mse', metrics=['mae'])
        
        return self.model
    
    def train(self, X_train, epochs=50, batch_size=32, validation_split=0.2):
        """
        Train the autoencoder on normal flight data.
        
        Args:
            X_train: Training sequences of shape (n_samples, sequence_length, n_features)
            epochs: Number of training epochs
            batch_size: Batch size for training
            validation_split: Fraction of data to use for validation
        """
        if self.model is None:
            self.build_model()
        
        # Scale features to prevent high loss values
        # Reshape for scaling: (samples, timesteps, features) -> (samples*timesteps, features)
        n_samples, n_timesteps, n_features = X_train.shape
        X_reshaped = X_train.reshape(-1, n_features)
        X_scaled = self.scaler.fit_transform(X_reshaped)
        X_train_scaled = X_scaled.reshape(n_samples, n_timesteps, n_features)
        
        # Callbacks for better training with ENHANCED early stopping
        early_stopping = keras.callbacks.EarlyStopping(
            monitor='val_loss',
            patience=15,  # INCREASED from 10 for more patience
            restore_best_weights=True,
            min_delta=0.0001
        )
        
        reduce_lr = keras.callbacks.ReduceLROnPlateau(
            monitor='val_loss',
            factor=0.5,
            patience=5,
            min_lr=0.00001,
            verbose=1
        )
        
        history = self.model.fit(
            X_train_scaled, X_train_scaled,
            epochs=epochs,
            batch_size=batch_size,
            validation_split=validation_split,
            callbacks=[early_stopping, reduce_lr],
            verbose=1
        )
        
        # Calculate reconstruction error threshold (95th percentile) on scaled data
        train_predictions = self.model.predict(X_train_scaled)
        train_errors = np.mean(np.abs(train_predictions - X_train_scaled), axis=(1, 2))
        self.threshold = np.percentile(train_errors, 95)
        
        return history
    
    def detect_anomaly(self, X):
        """
        Detect anomalies in flight sequences.
        
        Args:
            X: Sequences of shape (n_samples, sequence_length, n_features)
            
        Returns:
            anomaly_scores: Normalized anomaly scores (0-1)
            is_anomaly: Boolean array indicating anomalies
        """
        if self.model is None:
            raise ValueError("Model not trained. Call train() first.")
        
        # Scale input data using fitted scaler
        n_samples, n_timesteps, n_features = X.shape
        X_reshaped = X.reshape(-1, n_features)
        X_scaled = self.scaler.transform(X_reshaped)
        X_test_scaled = X_scaled.reshape(n_samples, n_timesteps, n_features)
        
        predictions = self.model.predict(X_test_scaled, verbose=0)
        errors = np.mean(np.abs(predictions - X_test_scaled), axis=(1, 2))
        
        # Normalize scores to 0-1 range
        anomaly_scores = np.clip(errors / (self.threshold * 2), 0, 1)
        is_anomaly = errors > self.threshold
        
        return anomaly_scores, is_anomaly
    
    def save(self, model_path='models/lstm_autoencoder.keras', 
             threshold_path='models/lstm_threshold.pkl'):
        """Save model and threshold."""
        os.makedirs(os.path.dirname(model_path), exist_ok=True)
        self.model.save(model_path)
        joblib.dump(self.threshold, threshold_path)
    
    def load(self, model_path='models/lstm_autoencoder.keras',
             threshold_path='models/lstm_threshold.pkl'):
        """Load model and threshold."""
        # Try new format first, then fall back to old format
        if not os.path.exists(model_path) and os.path.exists(model_path.replace('.keras', '.h5')):
            model_path = model_path.replace('.keras', '.h5')
        
        self.model = keras.models.load_model(model_path, compile=False)
        # Recompile with current Keras version
        self.model.compile(optimizer='adam', loss='mse', metrics=['mae'])
        
        self.threshold = joblib.load(threshold_path)
        
        # Extract parameters from model
        self.sequence_length = self.model.input_shape[1]
        self.n_features = self.model.input_shape[2]


def create_sequences(data, sequence_length=10):
    """
    Create sliding window sequences from flight data.
    
    Args:
        data: Array of shape (n_samples, n_features)
        sequence_length: Length of each sequence
        
    Returns:
        sequences: Array of shape (n_sequences, sequence_length, n_features)
    """
    sequences = []
    for i in range(len(data) - sequence_length + 1):
        sequences.append(data[i:i + sequence_length])
    return np.array(sequences)
