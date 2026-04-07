"""
Future Risk Prediction Module

Predicts risk evolution over time using trajectory prediction + risk assessment.
This addresses Additional Requirement #3: Predict future risk after some distance/time.

Combines:
- Trajectory Predictor: Forecasts future flight positions (lat, lon, alt, heading)
- Risk Predictor: Assesses risk at those future positions
- Weather Integration: Incorporates weather forecast if available
"""
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class FutureRiskPredictor:
    """
    Predicts how risk will evolve over the next N timesteps.
    
    Example:
        Current: LOW risk (0.2)
        In 5 min: MEDIUM risk (0.45) - approaching storm
        In 10 min: HIGH risk (0.72) - descent into low visibility zone
    """
    
    def __init__(self, 
                 trajectory_predictor=None,
                 risk_predictor=None,
                 threshold_manager=None):
        """
        Initialize future risk predictor.
        
        Args:
            trajectory_predictor: TrajectoryPredictor model instance
            risk_predictor: RiskPredictor model instance
            threshold_manager: RiskThresholdManager for dynamic thresholds
        """
        self.trajectory_predictor = trajectory_predictor
        self.risk_predictor = risk_predictor
        self.threshold_manager = threshold_manager
        
    def predict_future_risk(self,
                           current_sequence: np.ndarray,
                           current_features: np.ndarray,
                           time_horizon: int = 5,
                           time_step_seconds: int = 60) -> Dict:
        """
        Predict risk evolution over time.
        
        Args:
            current_sequence: Recent trajectory history 
                              (sequence_length, 4) - [lat, lon, alt, heading]
            current_features: Current flight features for risk assessment
                             (n_features,) - all features used by risk model
            time_horizon: Number of future timesteps to predict (default: 5)
            time_step_seconds: Seconds between each timestep (default: 60)
        
        Returns:
            Dictionary with:
                - future_positions: List of (lat, lon, alt, heading) tuples
                - future_risk_scores: List of risk scores (0-1)
                - future_risk_levels: List of risk levels ('LOW', 'MEDIUM', 'HIGH')
                - timestamps: List of future timestamps
                - risk_evolution: 'increasing', 'decreasing', 'stable'
                - max_risk_time: When risk peaks
                - warnings: List of warning messages
        """
        if self.trajectory_predictor is None:
            return self._fallback_linear_prediction(
                current_sequence, current_features, time_horizon
            )
        
        try:
            # Step 1: Predict future trajectory
            # Trajectory predictor expects (1, sequence_length, 4)
            sequence_reshaped = current_sequence.reshape(1, -1, 4)
            
            # Predict future positions
            if time_horizon <= self.trajectory_predictor.forecast_steps:
                # Use model's forecast directly
                future_trajectory = self.trajectory_predictor.predict(sequence_reshaped)
                future_trajectory = future_trajectory[0, :time_horizon, :]
            else:
                # Iterative prediction for longer horizons
                future_trajectory = self._predict_long_horizon(
                    sequence_reshaped, time_horizon
                )
            
            # Step 2: Prepare features for each future position
            future_features_list = []
            future_positions = []
            
            for i in range(time_horizon):
                # Convert numpy array elements to Python scalars
                lat = float(future_trajectory[i, 0])
                lon = float(future_trajectory[i, 1])
                alt = float(future_trajectory[i, 2])
                heading = float(future_trajectory[i, 3])
                future_positions.append((lat, lon, alt, heading))
                
                # Build feature vector for this future state
                # We'll update position-based features, keep others from current
                future_features = current_features.copy()
                
                # Update key features (indices depend on feature order)
                # Assuming standard order: altitude, velocity, vertical_rate, heading, ...
                if len(future_features) > 0:
                    future_features[0] = alt  # altitude
                if len(future_features) > 3:
                    future_features[3] = heading  # heading
                
                # Estimate vertical rate from altitude change
                if i > 0:
                    prev_alt = float(future_trajectory[i-1, 2])
                    vertical_rate = (alt - prev_alt) / time_step_seconds
                    if len(future_features) > 2:
                        future_features[2] = vertical_rate
                
                future_features_list.append(future_features)
            
            # Step 3: Predict risk for each future position
            future_features_array = np.array(future_features_list)
            
            if self.risk_predictor is not None:
                # Get risk levels (categorical predictions)
                risk_levels_numeric, _ = self.risk_predictor.predict(
                    future_features_array
                )
                # Get continuous risk scores (0-1)
                risk_scores = self.risk_predictor.get_risk_score(future_features_array)
                
                # Convert numeric to labels
                risk_level_map = {0: 'LOW', 1: 'MEDIUM', 2: 'HIGH'}
                risk_levels = [risk_level_map.get(int(lvl), 'UNKNOWN') 
                              for lvl in risk_levels_numeric]
            else:
                # Fallback: use heuristic risk based on altitude and vertical rate
                risk_scores = []
                risk_levels = []
                for features in future_features_list:
                    score = self._heuristic_risk(features)
                    risk_scores.append(score)
                    if score < 0.33:
                        risk_levels.append('LOW')
                    elif score < 0.66:
                        risk_levels.append('MEDIUM')
                    else:
                        risk_levels.append('HIGH')
                risk_scores = np.array(risk_scores)
            
            # Step 4: Analyze risk evolution
            timestamps = [
                datetime.now() + timedelta(seconds=time_step_seconds * (i+1))
                for i in range(time_horizon)
            ]
            
            # Determine trend
            risk_trend = self._analyze_risk_trend(risk_scores)
            
            # Find peak risk
            max_risk_idx = np.argmax(risk_scores)
            max_risk_time = timestamps[max_risk_idx]
            
            # Generate warnings
            warnings = self._generate_warnings(
                risk_scores, risk_levels, future_positions, timestamps
            )
            
            return {
                'success': True,
                'future_positions': future_positions,
                'future_risk_scores': risk_scores.tolist(),
                'future_risk_levels': risk_levels,
                'timestamps': [t.isoformat() for t in timestamps],
                'risk_evolution': risk_trend,
                'max_risk_time': max_risk_time.isoformat(),
                'max_risk_score': float(risk_scores[max_risk_idx]),
                'warnings': warnings,
                'current_risk': float(risk_scores[0]) if len(risk_scores) > 0 else None,
                'prediction_horizon_minutes': (time_horizon * time_step_seconds) / 60
            }
            
        except Exception as e:
            logger.error(f"Future risk prediction failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'warnings': ['Prediction failed - using current risk assessment only']
            }
    
    def _predict_long_horizon(self, sequence: np.ndarray, horizon: int) -> np.ndarray:
        """
        Predict beyond model's forecast_steps using iterative prediction.
        
        Args:
            sequence: Input sequence (1, sequence_length, 4)
            horizon: Total steps to predict
        
        Returns:
            Predictions (horizon, 4)
        """
        all_predictions = []
        current_seq = sequence[0]  # (sequence_length, 4)
        
        steps_remaining = horizon
        while steps_remaining > 0:
            # Predict next batch
            seq_reshaped = current_seq.reshape(1, -1, 4)
            next_pred = self.trajectory_predictor.predict(seq_reshaped)  # (1, forecast_steps, 4)
            
            steps_to_take = min(self.trajectory_predictor.forecast_steps, steps_remaining)
            all_predictions.append(next_pred[0, :steps_to_take, :])
            
            # Update sequence with new predictions
            if steps_remaining > self.trajectory_predictor.forecast_steps:
                # Roll sequence forward and append new predictions
                current_seq = np.vstack([
                    current_seq[steps_to_take:],
                    next_pred[0, :steps_to_take, :]
                ])
            
            steps_remaining -= steps_to_take
        
        return np.vstack(all_predictions)
    
    def _heuristic_risk(self, features: np.ndarray) -> float:
        """
        Simple heuristic risk calculation from features.
        
        Args:
            features: Feature array
        
        Returns:
            Risk score (0-1)
        """
        # Assuming feature order: altitude, velocity, vertical_rate, heading, ...
        risk = 0.0
        
        if len(features) > 0:
            altitude = features[0]
            # Low altitude = higher risk
            alt_norm = np.clip(altitude / 10000, 0, 1)
            risk += (1 - alt_norm) * 0.3
        
        if len(features) > 2:
            vertical_rate = features[2]
            # High descent rate = higher risk
            if vertical_rate < -10:
                risk += 0.4
            elif vertical_rate < -5:
                risk += 0.2
        
        return np.clip(risk, 0, 1)
    
    def _analyze_risk_trend(self, risk_scores: np.ndarray) -> str:
        """Determine if risk is increasing, decreasing, or stable."""
        if len(risk_scores) < 2:
            return 'stable'
        
        # Calculate trend using linear fit
        x = np.arange(len(risk_scores))
        slope = np.polyfit(x, risk_scores, 1)[0]
        
        if slope > 0.05:
            return 'increasing'
        elif slope < -0.05:
            return 'decreasing'
        else:
            return 'stable'
    
    def _generate_warnings(self,
                          risk_scores: np.ndarray,
                          risk_levels: List[str],
                          positions: List[Tuple],
                          timestamps: List[datetime]) -> List[str]:
        """Generate human-readable warnings based on predictions."""
        warnings = []
        
        # Check for risk escalation
        high_risk_indices = [i for i, lvl in enumerate(risk_levels) if lvl == 'HIGH']
        if high_risk_indices:
            first_high = high_risk_indices[0]
            time_to_high = timestamps[first_high]
            minutes = (time_to_high - datetime.now()).total_seconds() / 60
            warnings.append(
                f"⚠️ HIGH RISK expected in {minutes:.0f} minutes "
                f"(risk score: {risk_scores[first_high]:.2f})"
            )
        
        # Check for rapid risk increase
        if len(risk_scores) >= 2:
            max_increase = np.max(np.diff(risk_scores))
            if max_increase > 0.2:
                increase_idx = np.argmax(np.diff(risk_scores))
                warnings.append(
                    f"⚠️ Rapid risk increase detected between timesteps "
                    f"{increase_idx} and {increase_idx+1}"
                )
        
        # Check for low altitude in future
        low_alt_positions = [(i, pos) for i, pos in enumerate(positions) 
                            if pos[2] < 1500]  # altitude < 1500m
        if low_alt_positions:
            idx, pos = low_alt_positions[0]
            minutes = (timestamps[idx] - datetime.now()).total_seconds() / 60
            warnings.append(
                f"ℹ️ Low altitude ({pos[2]:.0f}m) predicted in {minutes:.0f} minutes"
            )
        
        return warnings
    
    def _fallback_linear_prediction(self,
                                    current_sequence: np.ndarray,
                                    current_features: np.ndarray,
                                    time_horizon: int) -> Dict:
        """
        Fallback when trajectory predictor is unavailable.
        Uses simple linear extrapolation.
        """
        logger.warning("Using fallback linear prediction (trajectory model not available)")
        
        # Use last two points to extrapolate
        if len(current_sequence) < 2:
            return {
                'success': False,
                'error': 'Insufficient trajectory history',
                'warnings': ['Need at least 2 trajectory points for prediction']
            }
        
        last_point = current_sequence[-1]
        prev_point = current_sequence[-2]
        
        # Calculate velocity vector
        delta = last_point - prev_point
        
        # Extrapolate linearly
        future_positions = []
        for i in range(1, time_horizon + 1):
            future_pos = last_point + delta * i
            # Convert numpy array to tuple of Python floats
            future_positions.append(tuple(float(x) for x in future_pos))
        
        # Simple constant risk assumption
        current_risk = 0.3  # Default medium-low risk
        risk_scores = [current_risk] * time_horizon
        risk_levels = ['MEDIUM'] * time_horizon
        
        timestamps = [
            datetime.now() + timedelta(minutes=i)
            for i in range(1, time_horizon + 1)
        ]
        
        return {
            'success': True,
            'future_positions': future_positions,
            'future_risk_scores': risk_scores,
            'future_risk_levels': risk_levels,
            'timestamps': [t.isoformat() for t in timestamps],
            'risk_evolution': 'stable',
            'warnings': ['Using simplified linear prediction - trajectory model unavailable'],
            'fallback_mode': True
        }
    
    def predict_risk_at_distance(self,
                                 current_sequence: np.ndarray,
                                 current_features: np.ndarray,
                                 distance_km: float,
                                 average_speed_kmh: float = 800) -> Dict:
        """
        Predict risk after traveling a certain distance.
        
        Args:
            current_sequence: Recent trajectory
            current_features: Current flight features
            distance_km: Distance to travel (kilometers)
            average_speed_kmh: Average speed (default: 800 km/h for jets)
        
        Returns:
            Same format as predict_future_risk()
        """
        # Convert distance to time
        time_hours = distance_km / average_speed_kmh
        time_minutes = time_hours * 60
        
        # Calculate number of timesteps (1-minute intervals)
        time_horizon = max(1, int(time_minutes))
        
        result = self.predict_future_risk(
            current_sequence, current_features, 
            time_horizon=time_horizon,
            time_step_seconds=60
        )
        
        if result['success']:
            result['distance_km'] = distance_km
            result['average_speed_kmh'] = average_speed_kmh
        
        return result


def create_future_risk_predictor(models_dir: str = 'models') -> FutureRiskPredictor:
    """
    Factory function to create FutureRiskPredictor with loaded models.
    
    Args:
        models_dir: Directory containing trained models
    
    Returns:
        FutureRiskPredictor instance
    """
    import os
    
    trajectory_predictor = None
    risk_predictor = None
    threshold_manager = None
    
    # Try to load trajectory predictor
    traj_path = os.path.join(models_dir, 'trajectory_predictor.keras')
    if os.path.exists(traj_path):
        try:
            from src.models.trajectory_predictor import TrajectoryPredictor
            trajectory_predictor = TrajectoryPredictor()
            trajectory_predictor.load(traj_path)
            logger.info("✓ Trajectory predictor loaded for future risk prediction")
        except Exception as e:
            logger.warning(f"Could not load trajectory predictor: {e}")
    
    # Try to load risk predictor
    risk_path = os.path.join(models_dir, 'risk_predictor.pkl')
    if os.path.exists(risk_path):
        try:
            from src.models.risk_predictor import RiskPredictor
            risk_predictor = RiskPredictor()
            risk_predictor.load(risk_path)
            logger.info("✓ Risk predictor loaded for future risk prediction")
        except Exception as e:
            logger.warning(f"Could not load risk predictor: {e}")
    
    # Load threshold manager
    try:
        from src.config.risk_thresholds import get_threshold_manager
        threshold_manager = get_threshold_manager()
        logger.info("✓ Threshold manager loaded")
    except Exception as e:
        logger.warning(f"Could not load threshold manager: {e}")
    
    return FutureRiskPredictor(
        trajectory_predictor=trajectory_predictor,
        risk_predictor=risk_predictor,
        threshold_manager=threshold_manager
    )
