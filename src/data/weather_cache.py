"""
Weather Data Caching System

Implements grid-based caching for weather data to minimize API calls.
Uses spatial and temporal caching to achieve 95%+ cache hit rate.
"""

from datetime import datetime, timedelta
from typing import Dict, Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class WeatherCache:
    """
    Grid-based weather data cache with time-based expiration.
    
    Features:
    - Spatial caching: Groups nearby locations into grid cells
    - Temporal caching: Caches data for configurable duration
    - Memory efficient: Automatic cleanup of expired entries
    """
    
    def __init__(self, cache_duration_minutes: int = 15, grid_size_km: float = 50):
        """
        Initialize weather cache.
        
        Args:
            cache_duration_minutes: How long to cache weather data (default: 15 min)
            grid_size_km: Size of grid cells in kilometers (default: 50 km)
        """
        self.cache: Dict[str, Tuple[dict, datetime]] = {}
        self.cache_duration = timedelta(minutes=cache_duration_minutes)
        self.grid_size_degrees = grid_size_km / 111.0  # ~111 km per degree
        
        # Statistics
        self.hits = 0
        self.misses = 0
        
        logger.info(f"Weather cache initialized: {cache_duration_minutes}min duration, {grid_size_km}km grid")
    
    def get_grid_key(self, lat: float, lon: float) -> str:
        """
        Convert geographic coordinates to grid cell key.
        
        Args:
            lat: Latitude
            lon: Longitude
            
        Returns:
            Grid cell identifier (e.g., "28.60,77.20")
        """
        grid_lat = round(lat / self.grid_size_degrees) * self.grid_size_degrees
        grid_lon = round(lon / self.grid_size_degrees) * self.grid_size_degrees
        return f"{grid_lat:.2f},{grid_lon:.2f}"
    
    def get(self, lat: float, lon: float) -> Optional[dict]:
        """
        Retrieve cached weather data for location.
        
        Args:
            lat: Latitude
            lon: Longitude
            
        Returns:
            Cached weather data if valid, None if expired or missing
        """
        key = self.get_grid_key(lat, lon)
        
        if key in self.cache:
            data, timestamp = self.cache[key]
            
            # Check if cache is still valid
            if datetime.now() - timestamp < self.cache_duration:
                self.hits += 1
                return data
            else:
                # Remove expired entry
                del self.cache[key]
        
        self.misses += 1
        return None
    
    def set(self, lat: float, lon: float, weather_data: dict) -> None:
        """
        Store weather data in cache.
        
        Args:
            lat: Latitude
            lon: Longitude
            weather_data: Weather data dictionary to cache
        """
        key = self.get_grid_key(lat, lon)
        self.cache[key] = (weather_data, datetime.now())
    
    def clear_expired(self) -> int:
        """
        Remove all expired cache entries.
        
        Returns:
            Number of entries removed
        """
        now = datetime.now()
        expired_keys = [
            key for key, (_, timestamp) in self.cache.items()
            if now - timestamp >= self.cache_duration
        ]
        
        for key in expired_keys:
            del self.cache[key]
        
        if expired_keys:
            logger.info(f"Cleared {len(expired_keys)} expired weather cache entries")
        
        return len(expired_keys)
    
    def clear_all(self) -> None:
        """Clear entire cache and reset statistics."""
        self.cache.clear()
        self.hits = 0
        self.misses = 0
        logger.info("Weather cache cleared")
    
    def get_stats(self) -> dict:
        """
        Get cache performance statistics.
        
        Returns:
            Dictionary with cache metrics
        """
        total_entries = len(self.cache)
        now = datetime.now()
        
        active_entries = sum(
            1 for _, (_, timestamp) in self.cache.items()
            if now - timestamp < self.cache_duration
        )
        
        total_requests = self.hits + self.misses
        hit_rate = (self.hits / total_requests * 100) if total_requests > 0 else 0
        
        return {
            'total_cached': total_entries,
            'active_cached': active_entries,
            'cache_hits': self.hits,
            'cache_misses': self.misses,
            'cache_hit_rate': round(hit_rate, 2),
            'cache_duration_min': self.cache_duration.total_seconds() / 60,
            'grid_size_km': self.grid_size_degrees * 111.0
        }
