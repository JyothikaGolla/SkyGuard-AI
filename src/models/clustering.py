"""
Flight pattern clustering using K-Means and DBSCAN.
Identifies common flight patterns and unusual behavior.
"""
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans, DBSCAN
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
import joblib
import os


class FlightClusterer:
    def __init__(self, n_clusters=5, method='kmeans'):
        """
        Initialize flight clusterer.
        
        Args:
            n_clusters: Number of clusters (for K-Means)
            method: 'kmeans' or 'dbscan'
        """
        self.n_clusters = n_clusters
        self.method = method
        self.model = None
        self.scaler = StandardScaler()
        self.pca = None
        
    def fit(self, X, use_pca=True, n_components=10):
        """
        Fit clustering model.
        
        Args:
            X: Feature matrix
            use_pca: Whether to use PCA for dimensionality reduction
            n_components: Number of PCA components
        """
        X_scaled = self.scaler.fit_transform(X)
        
        if use_pca and X.shape[1] > n_components:
            self.pca = PCA(n_components=n_components)
            X_transformed = self.pca.fit_transform(X_scaled)
        else:
            X_transformed = X_scaled
        
        if self.method == 'kmeans':
            self.model = KMeans(
                n_clusters=self.n_clusters,
                random_state=42,
                n_init=10
            )
        elif self.method == 'dbscan':
            self.model = DBSCAN(
                eps=0.5,
                min_samples=5,
                n_jobs=-1
            )
        
        self.model.fit(X_transformed)
        
    def predict(self, X):
        """
        Predict cluster labels.
        
        Args:
            X: Feature matrix
            
        Returns:
            labels: Cluster labels
        """
        X_scaled = self.scaler.transform(X)
        
        if self.pca is not None:
            X_transformed = self.pca.transform(X_scaled)
        else:
            X_transformed = X_scaled
        
        if self.method == 'kmeans':
            labels = self.model.predict(X_transformed)
        elif self.method == 'dbscan':
            # For DBSCAN, we need to fit on new data
            # Use closest cluster from training
            labels = self.model.fit_predict(X_transformed)
        
        return labels
    
    def get_cluster_distances(self, X):
        """
        Get distance to nearest cluster center.
        Useful for identifying unusual flights.
        
        Args:
            X: Feature matrix
            
        Returns:
            distances: Distance to nearest cluster
        """
        if self.method != 'kmeans':
            raise ValueError("Cluster distances only available for K-Means")
        
        X_scaled = self.scaler.transform(X)
        if self.pca is not None:
            X_transformed = self.pca.transform(X_scaled)
        else:
            X_transformed = X_scaled
        
        distances = self.model.transform(X_transformed).min(axis=1)
        return distances
    
    def get_cluster_statistics(self, X, labels):
        """
        Get statistics for each cluster.
        
        Args:
            X: Feature matrix
            labels: Cluster labels
            
        Returns:
            stats: Dictionary with cluster statistics
        """
        stats = {}
        for cluster in np.unique(labels):
            if cluster == -1:  # DBSCAN noise
                continue
            
            mask = labels == cluster
            cluster_data = X[mask]
            
            stats[int(cluster)] = {
                'size': int(mask.sum()),
                'mean': cluster_data.mean(axis=0).tolist(),
                'std': cluster_data.std(axis=0).tolist()
            }
        
        return stats
    
    def save(self, model_path='models/flight_clusterer.pkl'):
        """Save model, scaler, and PCA."""
        os.makedirs(os.path.dirname(model_path), exist_ok=True)
        joblib.dump({
            'model': self.model,
            'scaler': self.scaler,
            'pca': self.pca,
            'n_clusters': self.n_clusters,
            'method': self.method
        }, model_path)
    
    def load(self, model_path='models/flight_clusterer.pkl'):
        """Load model, scaler, and PCA."""
        data = joblib.load(model_path)
        self.model = data['model']
        self.scaler = data['scaler']
        self.pca = data.get('pca')
        self.n_clusters = data['n_clusters']
        self.method = data['method']
