"""
Dynamic Risk Threshold Configuration System

Enables variable thresholds based on:
- Flight phase (takeoff, landing, cruise)
- Altitude
- Weather conditions
- Aircraft type (if available)

This addresses Additional Requirement #1: Make thresholds variable instead of fixed
"""
import numpy as np
from typing import Dict, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class RiskThresholdManager:
    """
    Manages dynamic risk thresholds that adapt based on flight context.
    
    Default thresholds:
    - LOW: < 0.33
    - MEDIUM: 0.33 - 0.66
    - HIGH: > 0.66
    
    But these can be adjusted based on flight phase, altitude, weather, etc.
    """
    
    # Default baseline thresholds
    DEFAULT_LOW_THRESHOLD = 0.33
    DEFAULT_HIGH_THRESHOLD = 0.66
    
    # Flight phase adjustments (multipliers)
    PHASE_ADJUSTMENTS = {
        'takeoff': 0.85,      # Stricter: 0.28 / 0.56 (takeoff is risky)
        'landing': 0.80,      # Strictest: 0.26 / 0.53 (landing is most critical)
        'descent': 0.90,      # Stricter: 0.30 / 0.59
        'climb': 0.92,        # Slightly stricter: 0.30 / 0.61
        'cruise': 1.0,        # Normal: 0.33 / 0.66
        'unknown': 1.0        # Normal: 0.33 / 0.66
    }
    
    # Altitude-based adjustments (altitude in meters)
    ALTITUDE_ZONES = [
        (0, 500, 0.75),        # Ground level - very strict (0.25 / 0.50)
        (500, 1500, 0.80),     # Low altitude - strict (0.26 / 0.53)
        (1500, 3000, 0.85),    # Approach altitude - strict (0.28 / 0.56)
        (3000, 8000, 0.95),    # Medium altitude - slightly strict (0.31 / 0.63)
        (8000, 15000, 1.0),    # Safe cruise - normal (0.33 / 0.66)
        (15000, float('inf'), 1.05)  # High altitude - relaxed (0.35 / 0.69)
    ]
    
    # Weather-based adjustments
    WEATHER_ADJUSTMENTS = {
        'clear': 1.0,          # Normal
        'clouds': 0.98,        # Slightly stricter
        'rain': 0.90,          # Stricter: 0.30 / 0.59
        'thunderstorm': 0.75,  # Very strict: 0.25 / 0.50
        'snow': 0.85,          # Strict: 0.28 / 0.56
        'fog': 0.80,           # Very strict: 0.26 / 0.53
    }
    
    def __init__(self, 
                 base_low: float = None, 
                 base_high: float = None,
                 enable_phase_adjustment: bool = True,
                 enable_altitude_adjustment: bool = True,
                 enable_weather_adjustment: bool = True):
        """
        Initialize threshold manager.
        
        Args:
            base_low: Base LOW/MEDIUM threshold (default: 0.33)
            base_high: Base MEDIUM/HIGH threshold (default: 0.66)
            enable_phase_adjustment: Enable flight phase adjustments
            enable_altitude_adjustment: Enable altitude-based adjustments
            enable_weather_adjustment: Enable weather-based adjustments
        """
        self.base_low = base_low or self.DEFAULT_LOW_THRESHOLD
        self.base_high = base_high or self.DEFAULT_HIGH_THRESHOLD
        self.enable_phase_adj = enable_phase_adjustment
        self.enable_altitude_adj = enable_altitude_adjustment
        self.enable_weather_adj = enable_weather_adjustment
        
        logger.info(f"RiskThresholdManager initialized - Base: {self.base_low:.2f}/{self.base_high:.2f}")
    
    def get_thresholds(self, 
                       altitude: float = None,
                       flight_phase: str = None,
                       weather_condition: str = None) -> Tuple[float, float]:
        """
        Get dynamic risk thresholds based on flight context.
        
        Args:
            altitude: Current altitude in meters
            flight_phase: 'takeoff', 'landing', 'cruise', 'climb', 'descent'
            weather_condition: 'clear', 'clouds', 'rain', 'thunderstorm', etc.
        
        Returns:
            (low_threshold, high_threshold): Adjusted thresholds
        """
        low_threshold = self.base_low
        high_threshold = self.base_high
        
        adjustments_applied = []
        
        # Apply flight phase adjustment
        if self.enable_phase_adj and flight_phase:
            phase_mult = self.PHASE_ADJUSTMENTS.get(flight_phase.lower(), 1.0)
            low_threshold *= phase_mult
            high_threshold *= phase_mult
            if phase_mult != 1.0:
                adjustments_applied.append(f"phase:{flight_phase}({phase_mult:.2f})")
        
        # Apply altitude adjustment
        if self.enable_altitude_adj and altitude is not None:
            alt_mult = self._get_altitude_multiplier(altitude)
            low_threshold *= alt_mult
            high_threshold *= alt_mult
            if alt_mult != 1.0:
                adjustments_applied.append(f"altitude:{altitude:.0f}m({alt_mult:.2f})")
        
        # Apply weather adjustment
        if self.enable_weather_adj and weather_condition:
            weather_mult = self.WEATHER_ADJUSTMENTS.get(weather_condition.lower(), 1.0)
            low_threshold *= weather_mult
            high_threshold *= weather_mult
            if weather_mult != 1.0:
                adjustments_applied.append(f"weather:{weather_condition}({weather_mult:.2f})")
        
        # Log significant adjustments
        if adjustments_applied:
            logger.debug(f"Thresholds adjusted: {self.base_low:.2f}/{self.base_high:.2f} → "
                        f"{low_threshold:.2f}/{high_threshold:.2f} "
                        f"({', '.join(adjustments_applied)})")
        
        return (low_threshold, high_threshold)
    
    def _get_altitude_multiplier(self, altitude: float) -> float:
        """Get altitude-based threshold multiplier."""
        for alt_min, alt_max, multiplier in self.ALTITUDE_ZONES:
            if alt_min <= altitude < alt_max:
                return multiplier
        return 1.0
    
    def classify_risk(self, 
                     risk_score: float,
                     altitude: float = None,
                     flight_phase: str = None,
                     weather_condition: str = None) -> str:
        """
        Classify risk level using dynamic thresholds.
        
        Args:
            risk_score: Continuous risk score (0-1)
            altitude: Current altitude in meters
            flight_phase: Flight phase
            weather_condition: Weather condition
        
        Returns:
            'LOW', 'MEDIUM', or 'HIGH'
        """
        low_thresh, high_thresh = self.get_thresholds(altitude, flight_phase, weather_condition)
        
        if risk_score < low_thresh:
            return 'LOW'
        elif risk_score < high_thresh:
            return 'MEDIUM'
        else:
            return 'HIGH'
    
    def classify_risk_batch(self,
                           risk_scores: np.ndarray,
                           altitudes: np.ndarray = None,
                           flight_phases: np.ndarray = None,
                           weather_conditions: np.ndarray = None) -> np.ndarray:
        """
        Classify risk levels for multiple flights using dynamic thresholds.
        
        Args:
            risk_scores: Array of risk scores
            altitudes: Array of altitudes
            flight_phases: Array of flight phases
            weather_conditions: Array of weather conditions
        
        Returns:
            Array of risk level strings
        """
        n = len(risk_scores)
        risk_levels = np.empty(n, dtype='<U10')  # String array
        
        for i in range(n):
            altitude = altitudes[i] if altitudes is not None else None
            phase = flight_phases[i] if flight_phases is not None else None
            weather = weather_conditions[i] if weather_conditions is not None else None
            
            risk_levels[i] = self.classify_risk(
                risk_scores[i], altitude, phase, weather
            )
        
        return risk_levels
    
    def get_threshold_info(self) -> Dict:
        """Get current threshold configuration as dict."""
        return {
            'base_thresholds': {
                'low': self.base_low,
                'high': self.base_high
            },
            'adjustments_enabled': {
                'phase': self.enable_phase_adj,
                'altitude': self.enable_altitude_adj,
                'weather': self.enable_weather_adj
            },
            'phase_multipliers': self.PHASE_ADJUSTMENTS,
            'altitude_zones': [
                {'min': z[0], 'max': z[1], 'multiplier': z[2]}
                for z in self.ALTITUDE_ZONES
            ],
            'weather_multipliers': self.WEATHER_ADJUSTMENTS
        }


# Global singleton instance for easy access
_default_manager = None

def get_threshold_manager() -> RiskThresholdManager:
    """Get or create the default threshold manager instance."""
    global _default_manager
    if _default_manager is None:
        _default_manager = RiskThresholdManager()
    return _default_manager


def set_base_thresholds(low: float, high: float):
    """Set new base thresholds globally."""
    global _default_manager
    _default_manager = RiskThresholdManager(base_low=low, base_high=high)
    logger.info(f"Base thresholds updated: {low:.2f} / {high:.2f}")
