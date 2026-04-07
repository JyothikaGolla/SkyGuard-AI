import sys
import os

# Add project root to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

from flask import Flask, jsonify, request
from flask import make_response
from flask_cors import CORS
import numpy as np
import pandas as pd
import logging
import traceback
from src.data.fetch_opensky import fetch_flights, DEFAULT_BBOX
from src.data.fetch_weather import WeatherService
from src.features.build_features import build_featured_flights

# Import authentication and user management blueprints
from src.auth.routes import auth_bp
from src.user.routes import user_bp
from src.admin.routes import admin_bp
from src.auth.jwt_utils import token_required
from src.database.models import init_db, AuditLog, SystemMetrics, AnalyticsHistory
from datetime import datetime

# Setup logging first
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Initialize database
try:
    engine, SessionLocal = init_db()
    logger.info("✓ Database initialized successfully")
except Exception as e:
    logger.error(f"Database initialization failed: {e}")
    SessionLocal = None

# Register blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(user_bp)
app.register_blueprint(admin_bp)

# Audit logging middleware
@app.before_request
def log_request():
    """Log request start time for duration tracking."""
    request.start_time = datetime.utcnow()

@app.after_request
def log_response(response):
    """Log request completion and save audit trail."""
    if not SessionLocal or not request.endpoint or request.endpoint.startswith('static'):
        return response
    
    # Skip OPTIONS requests (CORS preflight checks)
    if request.method == 'OPTIONS':
        return response
    
    db = SessionLocal()
    try:
        duration = (datetime.utcnow() - request.start_time).total_seconds() * 1000
        
        # Get user if authenticated
        user_id = None
        if hasattr(request, 'current_user') and request.current_user:
            user_id = request.current_user.get('user_id') or request.current_user.get('id')
        
        # Create audit log entry
        audit_log = AuditLog(
            user_id=user_id,
            action=request.method,
            resource=request.path,
            details={
                'endpoint': request.endpoint,
                'method': request.method,
                'args': dict(request.args),
                'duration_ms': round(duration, 2)
            },
            ip_address=request.remote_addr or 'unknown',
            user_agent=request.headers.get('User-Agent', '')[:255],
            success=response.status_code < 400,
            error_message=None if response.status_code < 400 else f"Status {response.status_code}"
        )
        db.add(audit_log)
        
        # Update system metrics
        metric = db.query(SystemMetrics).filter(
            SystemMetrics.api_endpoint == request.endpoint,
            SystemMetrics.metric_date == datetime.utcnow().date(),
            SystemMetrics.period == 'daily'
        ).first()
        
        if metric:
            metric.request_count += 1
            if response.status_code >= 400:
                metric.error_count += 1
            # Update rolling average
            metric.avg_response_time = round(
                (metric.avg_response_time * (metric.request_count - 1) + duration) / 
                metric.request_count, 2
            )
        else:
            metric = SystemMetrics(
                api_endpoint=request.endpoint,
                request_count=1,
                error_count=1 if response.status_code >= 400 else 0,
                avg_response_time=round(duration, 2),
                metric_date=datetime.utcnow().date(),
                period='daily'
            )
            db.add(metric)
        
        db.commit()
    except Exception as e:
        logger.error(f"Audit logging error: {e}")
        db.rollback()
    finally:
        db.close()
    
    return response

# Lazy load ML models and weather service
_models = None
_weather_service = None

def get_models():
    """Lazy load ML models."""
    global _models
    if _models is None:
        try:
            from src.models.inference import get_model_instance
            _models = get_model_instance()
            logger.info("ML models loaded successfully")
        except Exception as e:
            logger.warning(f"ML models not available: {e}")
            _models = False  # Mark as unavailable
    return _models if _models else None

def get_weather_service():
    """Lazy load weather service."""
    global _weather_service
    if _weather_service is None:
        try:
            api_key = os.environ.get('OPENWEATHER_API_KEY')
            if not api_key:
                logger.warning("OPENWEATHER_API_KEY not set - weather features will use defaults")
                return None
            logger.info("Initializing weather service...")
            _weather_service = WeatherService(api_key)
            logger.info("✓ Weather service initialized")
        except Exception as e:
            logger.warning(f"Could not initialize weather service: {e}")
            return None
    return _weather_service

@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})

@app.route("/api/flights", methods=["GET"])
@token_required
def get_flights():
    """
    Return live flights with advanced ML-based risk/anomaly scores.
    Requires authentication.

    Optional query params:
    - bbox: "min_lat,max_lat,min_lon,max_lon"
    - use_ml: "true" to force ML predictions (default: auto)
    """
    logger.info(f"Flight fetch by user: {request.current_user['username']} ({request.current_user['email']})")
    bbox_param = request.args.get("bbox", None)
    use_ml = request.args.get("use_ml", "auto").lower()
    
    if bbox_param:
        try:
            parts = [float(x.strip()) for x in bbox_param.split(",")]
            if len(parts) != 4:
                raise ValueError
            bbox = tuple(parts)
        except ValueError:
            return make_response(jsonify({"error": "Invalid bbox format"}), 400)
    else:
        bbox = DEFAULT_BBOX

    try:
        raw = fetch_flights(bbox=bbox)
    except Exception as e:
        logger.error(f"Failed to fetch flights: {e}")
        return make_response(jsonify({"error": str(e)}), 500)

    if raw.empty:
        return jsonify([])

    # Fetch weather data for all flights
    weather_service = get_weather_service()
    if weather_service:
        try:
            raw = weather_service.get_weather_for_flights(raw)
            stats = weather_service.get_usage_stats()
            logger.info(f"Weather: {stats['api_calls_today']} API calls, {stats['cache_hit_rate']:.1f}% cache hit rate")
        except Exception as e:
            logger.warning(f"Weather fetch failed: {e} - using defaults")

    # Build features (includes weather features if available)
    featured = build_featured_flights(raw)
    
    # Try ML predictions if available
    models = get_models()
    ml_predictions = {}
    
    # Always attempt to use ML (auto mode)
    use_ml = request.args.get("use_ml", "auto")
    
    logger.info(f"Models loaded: {models is not None}, use_ml param: {use_ml}")
    
    if models and (use_ml == "true" or use_ml == "auto"):
        try:
            # Prepare features for ML (21 features - removed altitude_bin and weather_risk_score)
            feature_cols = [
                # Flight dynamics (11 features)
                'altitude', 'velocity', 'vertical_rate', 'heading',
                'speed_kmh', 'is_climbing', 'is_descending',
                'speed_variation', 'altitude_change_rate', 'heading_change_rate',
                'acceleration', 'time_since_last_update',
                # Weather features (9 features)
                'temperature', 'wind_speed', 'visibility',
                'crosswind', 'headwind', 'severe_weather', 'low_visibility',
                'high_winds', 'icing_risk'
            ]
            available_cols = [col for col in feature_cols if col in featured.columns]
            X = featured[available_cols].fillna(0).values
            
            # ML-based risk prediction
            risk_scores, risk_levels = models.predict_risk(X)
            if risk_scores is not None:
                ml_predictions['ml_risk_score'] = risk_scores
                ml_predictions['ml_risk_level'] = risk_levels
                
                # Map ML risk levels to strings and update featured dataframe
                risk_level_map = {0: 'LOW', 1: 'MEDIUM', 2: 'HIGH'}
                featured['risk_level'] = [risk_level_map.get(int(lvl), 'UNKNOWN') for lvl in risk_levels]
                featured['risk_score'] = risk_scores
                
                # Debug: Log risk level distribution
                risk_dist = featured['risk_level'].value_counts().to_dict()
                logger.info(f"ML Risk Distribution: {risk_dist}")
                
                logger.info(f"✓ Applied ML risk predictions to {len(featured)} flights")
            
            # Isolation Forest anomaly detection
            is_outlier, outlier_scores = models.detect_anomalies_isolation(X)
            if outlier_scores is not None:
                ml_predictions['ml_anomaly_score'] = outlier_scores
                ml_predictions['ml_is_outlier'] = is_outlier
                
                # Update featured dataframe with ML anomaly scores
                featured['anomaly_score'] = outlier_scores
                # Update anomaly level based on ML scores
                def anomaly_bucket(x):
                    if x < 0.33:
                        return "LOW"
                    elif x < 0.66:
                        return "MEDIUM"
                    return "HIGH"
                featured['anomaly_level'] = [anomaly_bucket(score) for score in outlier_scores]
                
                logger.info(f"✓ Applied Isolation Forest to {len(featured)} flights")
            
            # Clustering
            cluster_labels = models.predict_cluster(X)
            if cluster_labels is not None:
                ml_predictions['cluster'] = cluster_labels
                
                # Update featured dataframe with cluster labels
                featured['cluster'] = cluster_labels
                
                logger.info(f"✓ Applied clustering to {len(featured)} flights")
                
        except Exception as e:
            logger.error(f"ML prediction error: {e}")
    
    # Build response
    records = []
    for idx, row in featured.iterrows():
        record = {
            "icao24": row["icao24"],
            "callsign": row["callsign"],
            "origin_country": row["origin_country"],
            "lat": row["lat"],
            "lon": row["lon"],
            "altitude": float(row["altitude"]) if row["altitude"] == row["altitude"] else None,
            "velocity": float(row["velocity"]) if row["velocity"] == row["velocity"] else None,
            "vertical_rate": float(row["vertical_rate"]) if row["vertical_rate"] == row["vertical_rate"] else None,
            "heading": float(row["heading"]) if row["heading"] == row["heading"] else None,
            
            # Heuristic scores (always available)
            "risk_score": float(row["risk_score"]),
            "anomaly_score": float(row["anomaly_score"]),
            "risk_level": row["risk_level"],
            "anomaly_level": row.get("anomaly_level", "UNKNOWN"),
            
            # Additional features
            "speed_kmh": float(row["speed_kmh"]),
            "flight_phase": row.get("flight_phase", "unknown"),
            "is_climbing": bool(row["is_climbing"]),
            "is_descending": bool(row["is_descending"]),
            
            # Weather data (if available)
            "weather": {
                "condition": row.get("weather_condition", "Clear"),
                "temperature": float(row["temperature"]) if "temperature" in row and row["temperature"] == row["temperature"] else None,
                "wind_speed": float(row["wind_speed"]) if "wind_speed" in row and row["wind_speed"] == row["wind_speed"] else None,
                "visibility": float(row["visibility"]) if "visibility" in row and row["visibility"] == row["visibility"] else None,
                "weather_risk_score": float(row["weather_risk_score"]) if "weather_risk_score" in row else 0,
                "severe_weather": bool(row.get("severe_weather", False)),
                "low_visibility": bool(row.get("low_visibility", False)),
                "high_winds": bool(row.get("high_winds", False)),
                "icing_risk": bool(row.get("icing_risk", False)),
            } if "temperature" in row else None,
        }
        
        # Add ML predictions if available
        if 'ml_risk_score' in ml_predictions:
            idx_pos = list(featured.index).index(idx)
            record['ml_risk_score'] = float(ml_predictions['ml_risk_score'][idx_pos])
            risk_level_map = {0: 'LOW', 1: 'MEDIUM', 2: 'HIGH'}
            record['ml_risk_level'] = risk_level_map.get(
                int(ml_predictions['ml_risk_level'][idx_pos]), 'UNKNOWN'
            )
        
        if 'ml_anomaly_score' in ml_predictions:
            idx_pos = list(featured.index).index(idx)
            record['ml_anomaly_score'] = float(ml_predictions['ml_anomaly_score'][idx_pos])
            record['ml_is_outlier'] = bool(ml_predictions['ml_is_outlier'][idx_pos])
        
        if 'cluster' in ml_predictions:
            idx_pos = list(featured.index).index(idx)
            record['cluster'] = int(ml_predictions['cluster'][idx_pos])
        
        records.append(record)

    return jsonify(records)


@app.route("/api/analytics", methods=["GET"])
@token_required
def get_analytics():
    """
    Get advanced analytics and statistics about current flights.
    Requires authentication. Saves query to user's analytics history.
    
    Returns aggregated metrics, patterns, and insights.
    """
    logger.info(f"Analytics request by user: {request.current_user.username}")
    bbox_param = request.args.get("bbox", None)
    if bbox_param:
        try:
            parts = [float(x.strip()) for x in bbox_param.split(",")]
            if len(parts) != 4:
                raise ValueError
            bbox = tuple(parts)
        except ValueError:
            return make_response(jsonify({"error": "Invalid bbox format"}), 400)
    else:
        bbox = DEFAULT_BBOX
    
    try:
        raw = fetch_flights(bbox=bbox)
        if raw.empty:
            return jsonify({"total_flights": 0})
        
        # Fetch weather data for all flights
        weather_service = get_weather_service()
        if weather_service:
            try:
                raw = weather_service.get_weather_for_flights(raw)
            except Exception as e:
                logger.warning(f"Analytics weather fetch failed: {e}")
        
        featured = build_featured_flights(raw)
        
        # Apply ML predictions to analytics (same as /api/flights)
        models = get_models()
        if models:
            try:
                feature_cols = [
                    'altitude', 'velocity', 'vertical_rate', 'heading',
                    'speed_kmh', 'is_climbing', 'is_descending', 'altitude_bin',
                    'speed_variation', 'altitude_change_rate', 'heading_change_rate',
                    'acceleration', 'time_since_last_update',
                    'temperature', 'wind_speed', 'visibility', 'weather_risk_score',
                    'crosswind', 'headwind', 'severe_weather', 'low_visibility',
                    'high_winds', 'icing_risk'
                ]
                available_cols = [col for col in feature_cols if col in featured.columns]
                X = featured[available_cols].fillna(0).values
                
                # ML-based risk prediction
                risk_scores, risk_levels = models.predict_risk(X)
                if risk_scores is not None:
                    risk_level_map = {0: 'LOW', 1: 'MEDIUM', 2: 'HIGH'}
                    featured['risk_level'] = [risk_level_map.get(int(lvl), 'UNKNOWN') for lvl in risk_levels]
                    featured['risk_score'] = risk_scores
                    logger.info(f"Analytics: ML predictions applied ({featured['risk_level'].value_counts().to_dict()})")
            except Exception as e:
                logger.warning(f"Analytics ML predictions failed: {e}")
        
        # Calculate analytics
        analytics = {
            "total_flights": len(featured),
            "by_country": featured["origin_country"].value_counts().head(10).to_dict(),
            "by_risk_level": featured["risk_level"].value_counts().to_dict(),
            "by_flight_phase": featured.get("flight_phase", pd.Series()).value_counts().to_dict(),
            
            "altitude_stats": {
                "mean": float(featured["altitude"].mean()),
                "median": float(featured["altitude"].median()),
                "max": float(featured["altitude"].max()),
                "min": float(featured["altitude"].min()),
                "distribution": {
                    "0-1k": int((featured["altitude"] < 1000).sum()),
                    "1-5k": int(((featured["altitude"] >= 1000) & (featured["altitude"] < 5000)).sum()),
                    "5-10k": int(((featured["altitude"] >= 5000) & (featured["altitude"] < 10000)).sum()),
                    "10-20k": int(((featured["altitude"] >= 10000) & (featured["altitude"] < 20000)).sum()),
                    "20k+": int((featured["altitude"] >= 20000).sum()),
                }
            },
            
            "speed_stats": {
                "mean_kmh": float(featured["speed_kmh"].mean()),
                "median_kmh": float(featured["speed_kmh"].median()),
                "max_kmh": float(featured["speed_kmh"].max()),
            },
            
            "risk_stats": {
                "mean_risk_score": float(featured["risk_score"].mean()),
                "high_risk_count": int((featured["risk_level"] == "HIGH").sum()),
                "medium_risk_count": int((featured["risk_level"] == "MEDIUM").sum()),
                "low_risk_count": int((featured["risk_level"] == "LOW").sum()),
            },
            
            "anomaly_stats": {
                "mean_anomaly_score": float(featured["anomaly_score"].mean()),
                "high_anomaly_count": int((featured["anomaly_score"] > 0.66).sum()),
            },
            
            # Weather analytics
            "weather_stats": {
                "mean_temperature": float(featured["temperature"].mean()) if "temperature" in featured.columns else None,
                "mean_wind_speed": float(featured["wind_speed"].mean()) if "wind_speed" in featured.columns else None,
                "mean_visibility": float(featured["visibility"].mean()) if "visibility" in featured.columns else None,
                "mean_weather_risk": float(featured["weather_risk_score"].mean()) if "weather_risk_score" in featured.columns else None,
                "severe_weather_count": int(featured["severe_weather"].sum()) if "severe_weather" in featured.columns else 0,
                "low_visibility_count": int(featured["low_visibility"].sum()) if "low_visibility" in featured.columns else 0,
                "high_winds_count": int(featured["high_winds"].sum()) if "high_winds" in featured.columns else 0,
                "icing_risk_count": int(featured["icing_risk"].sum()) if "icing_risk" in featured.columns else 0,
                "flights_with_weather": int(featured["temperature"].notna().sum()) if "temperature" in featured.columns else 0,
            }
        }
        
        # Add ML-specific analytics if models available
        models = get_models()
        if models:
            try:
                # Use same feature columns as in /api/flights
                feature_cols = [
                    # Flight dynamics (13 features)
                    'altitude', 'velocity', 'vertical_rate', 'heading',
                    'speed_kmh', 'is_climbing', 'is_descending', 'altitude_bin',
                    'speed_variation', 'altitude_change_rate', 'heading_change_rate',
                    'acceleration', 'time_since_last_update',
                    # Weather features (11 features) - now integrated in XGBoost
                    'temperature', 'wind_speed', 'visibility', 'pressure', 'humidity',
                    'crosswind', 'headwind', 'severe_weather', 'low_visibility',
                    'high_winds', 'icing_risk'
                ]
                available_cols = [col for col in feature_cols if col in featured.columns]
                X = featured[available_cols].fillna(0).values
                
                # Cluster analysis
                cluster_labels = models.predict_cluster(X)
                if cluster_labels is not None:
                    unique, counts = np.unique(cluster_labels, return_counts=True)
                    analytics["cluster_distribution"] = {
                        f"cluster_{int(u)}": int(c) for u, c in zip(unique, counts)
                    }
                
                # ML anomaly detection
                is_outlier, _ = models.detect_anomalies_isolation(X)
                if is_outlier is not None:
                    analytics["ml_outlier_count"] = int(is_outlier.sum())
                    
            except Exception as e:
                logger.error(f"ML analytics error: {e}")
        
        # Save to user's analytics history
        if SessionLocal:
            db = SessionLocal()
            try:
                history = AnalyticsHistory(
                    user_id=request.current_user.id,
                    query_type='advanced_analytics',
                    query_params={'bbox': bbox_param or 'default'},
                    total_flights=analytics['total_flights'],
                    high_risk_count=analytics['risk_stats']['high_risk_count'],
                    anomaly_count=analytics['anomaly_stats']['high_anomaly_count'],
                    analytics_data=analytics
                )
                db.add(history)
                db.commit()
                logger.info(f"✓ Analytics saved to history for {request.current_user.username}")
            except Exception as e:
                logger.error(f"Failed to save analytics history: {e}")
                db.rollback()
            finally:
                db.close()
        
        return jsonify(analytics)
        
    except Exception as e:
        logger.error(f"Analytics error: {e}")
        return make_response(jsonify({"error": str(e)}), 500)


@app.route("/api/model-status", methods=["GET"])
def get_model_status():
    """Check which ML models are loaded and available."""
    models = get_models()
    
    status = {
        "models_available": models is not None,
        "loaded_models": {}
    }
    
    if models:
        status["loaded_models"] = {
            "lstm_autoencoder": models.lstm_autoencoder is not None,
            "risk_predictor": models.risk_predictor is not None,
            "isolation_forest": models.isolation_forest is not None,
            "trajectory_predictor": models.trajectory_predictor is not None,
            "clusterer": models.clusterer is not None,
        }
    
    return jsonify(status)


@app.route("/api/monitoring/check-watchlists", methods=["POST"])
@token_required
def check_watchlists():
    """
    Manually trigger watchlist monitoring (admin only recommended).
    Checks all active watchlists and sends alerts.
    """
    try:
        from src.monitoring.watchlist_monitor import get_watchlist_monitor
        
        monitor = get_watchlist_monitor()
        stats = monitor.check_all_watchlists()
        
        return jsonify({
            "message": "Watchlist monitoring completed",
            "stats": stats
        }), 200
        
    except Exception as e:
        logger.error(f"Monitoring error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/email/test", methods=["POST"])
@token_required
def test_email():
    """
    Test email configuration by sending a test email to the current user.
    """
    try:
        from src.email.email_service import get_email_service
        
        email_service = get_email_service()
        
        if not email_service.is_configured:
            return jsonify({
                "error": "Email service not configured. Please set SMTP_USER and SMTP_PASSWORD in .env file"
            }), 400
        
        # Get current user
        user_email = request.current_user.get('email')
        user_name = request.current_user.get('full_name') or request.current_user.get('username')
        
        # Send test alert
        success = email_service.send_flight_alert(
            user_email=user_email,
            user_name=user_name,
            alert_data={
                'title': 'Test Alert - Email Configuration Successful',
                'message': 'This is a test email to verify your SkyGuard AI email alert configuration is working correctly.',
                'severity': 'MEDIUM',
                'flight_data': {
                    'callsign': 'TEST123',
                    'icao24': 'test24',
                    'origin_country': 'Test Country',
                    'risk_score': 0.75
                }
            }
        )
        
        if success:
            return jsonify({"message": f"Test email sent successfully to {user_email}"}), 200
        else:
            return jsonify({"error": "Failed to send test email. Check server logs for details."}), 500
            
    except Exception as e:
        logger.error(f"Test email error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/flights/<icao24>/explain", methods=["GET", "POST"])
@token_required
def explain_flight_risk(icao24):
    """
    Get SHAP-based explanation for why a flight has its risk classification.
    Returns top contributing features and their impact on the prediction.
    """
    try:
        # Check if flight data was sent directly (POST method)
        if request.method == "POST":
            data = request.get_json()
            flight_data_dict = data.get('flight_data', {})
            provided_risk_level = data.get('risk_level')
            provided_risk_score = data.get('risk_score')
            
            # Extract features directly from the provided flight data
            feature_cols = [
                'altitude', 'velocity', 'vertical_rate', 'heading',
                'speed_kmh', 'is_climbing', 'is_descending',
                'speed_variation', 'altitude_change_rate', 'heading_change_rate',
                'acceleration', 'time_since_last_update'
            ]
            weather_cols = [
                'temperature', 'wind_speed', 'visibility',
                'crosswind', 'headwind', 'severe_weather', 'low_visibility',
                'high_winds', 'icing_risk'
            ]
            
            # Build feature array from flight data
            X_values = []
            for col in feature_cols:
                X_values.append(flight_data_dict.get(col, 0))
            
            # Add weather features
            weather = flight_data_dict.get('weather', {})
            for col in weather_cols:
                X_values.append(weather.get(col, 0))
            
            X = np.array([X_values])
            available_cols = feature_cols + weather_cols
            callsign = flight_data_dict.get('callsign', icao24)
            
        else:
            # Legacy GET method - full data fetch (slower)
            provided_risk_level = request.args.get('risk_level')
            provided_risk_score = request.args.get('risk_score', type=float)
            
            # Get current flight data
            raw = fetch_flights(bbox=DEFAULT_BBOX)
            if raw.empty or icao24 not in raw['icao24'].values:
                return jsonify({"error": "Flight not found"}), 404
            
            # Get the specific flight
            flight_data = raw[raw['icao24'] == icao24].iloc[0]
            callsign = flight_data.get('callsign', icao24)
            
            # Fetch weather
            weather_service = get_weather_service()
            if weather_service:
                try:
                    raw = weather_service.get_weather_for_flights(raw)
                except:
                    pass
            
            # Build features
            featured = build_featured_flights(raw)
            flight_features = featured[featured['icao24'] == icao24].iloc[0]
            
            # Prepare features
            feature_cols = [
                'altitude', 'velocity', 'vertical_rate', 'heading',
                'speed_kmh', 'is_climbing', 'is_descending',
                'speed_variation', 'altitude_change_rate', 'heading_change_rate',
                'acceleration', 'time_since_last_update',
                'temperature', 'wind_speed', 'visibility',
                'crosswind', 'headwind', 'severe_weather', 'low_visibility',
                'high_winds', 'icing_risk'
            ]
            available_cols = [col for col in feature_cols if col in flight_features.index]
            X = np.array([flight_features[available_cols].fillna(0).values])
        
        # Get models (only needed for GET method fallback prediction)
        models = get_models()
        if not models:
            return jsonify({"error": "ML models not loaded"}), 503
        
        # Get prediction (use provided values if available)
        if provided_risk_level and provided_risk_score is not None:
            predicted_risk = provided_risk_level
            risk_score = provided_risk_score
            # Map risk level back to numeric for SHAP
            risk_level_numeric = {'LOW': 0, 'MEDIUM': 1, 'HIGH': 2}.get(provided_risk_level, 0)
        else:
            risk_scores, risk_levels = models.predict_risk(X)
            risk_level_map = {0: 'LOW', 1: 'MEDIUM', 2: 'HIGH'}
            predicted_risk = risk_level_map.get(int(risk_levels[0]), 'UNKNOWN')
            risk_score = float(risk_scores[0])
            risk_level_numeric = int(risk_levels[0])
        
        # Calculate SHAP explanation
        try:
            import shap
            import joblib
            
            # Load the XGBoost model
            model_data = joblib.load('models/risk_predictor.pkl')
            xgb_model = model_data['model'] if isinstance(model_data, dict) else model_data
            
            # Create SHAP explainer
            explainer = shap.TreeExplainer(xgb_model)
            shap_values = explainer.shap_values(X)
            
            # Get base value (average prediction)
            base_value = explainer.expected_value
            if isinstance(base_value, (list, np.ndarray)):
                base_value = float(base_value[risk_level_numeric])
            
            # Get SHAP values for the predicted class
            if isinstance(shap_values, list):
                class_shap = shap_values[risk_level_numeric][0]
            else:
                class_shap = shap_values[0]
            
            # Create feature importance list
            feature_importance = []
            for i, feature_name in enumerate(available_cols):
                feature_value = float(X[0][i])
                # Handle both 1D and multi-dimensional SHAP values
                if hasattr(class_shap[i], '__len__') and len(class_shap[i]) > 1:
                    shap_value = float(class_shap[i][0])  # Take first element if multi-dim
                else:
                    shap_value = float(class_shap[i])
                
                # Replace inf/nan with safe values for JSON serialization
                if np.isnan(feature_value) or np.isinf(feature_value):
                    feature_value = 0.0
                if np.isnan(shap_value) or np.isinf(shap_value):
                    shap_value = 0.0
                
                feature_importance.append({
                    'feature': feature_name,
                    'value': feature_value,
                    'impact': shap_value,
                    'impact_direction': 'increases' if shap_value > 0 else 'decreases'
                })
            
            # Sort by absolute impact
            feature_importance.sort(key=lambda x: abs(x['impact']), reverse=True)
            
            # Get top 5 features
            top_features = feature_importance[:5]
            
            # Create human-readable explanations
            explanations = []
            for feat in top_features:
                direction = "increasing" if feat['impact'] > 0 else "decreasing"
                val = round(feat['value'], 2) if not (np.isnan(feat['value']) or np.isinf(feat['value'])) else 0.0
                imp = round(feat['impact'], 4) if not (np.isnan(feat['impact']) or np.isinf(feat['impact'])) else 0.0
                explanations.append({
                    'feature': feat['feature'],
                    'value': val,
                    'impact': imp,
                    'explanation': f"{feat['feature'].replace('_', ' ').title()} ({val:.1f}) is {direction} risk"
                })
            
            # Ensure base_value and risk_score are safe for JSON
            base_val = float(base_value)
            if np.isnan(base_val) or np.isinf(base_val):
                base_val = 0.5
            
            risk_score_safe = float(risk_score)
            if np.isnan(risk_score_safe) or np.isinf(risk_score_safe):
                risk_score_safe = 0.5
            
            return jsonify({
                'icao24': icao24,
                'callsign': callsign,
                'risk_level': predicted_risk,
                'risk_score': risk_score_safe,
                'base_prediction': base_val,
                'top_factors': explanations,
                'all_features': feature_importance[:10]  # Top 10 for detailed view
            }), 200
            
        except ImportError:
            # SHAP not available, return basic explanation
            basic_factors = []
            for i, col in enumerate(available_cols[:5]):
                val = float(X[0][i])
                # Replace inf/nan with safe values
                if np.isnan(val) or np.isinf(val):
                    val = 0.0
                basic_factors.append({'feature': col, 'value': val})
            
            # Ensure risk_score is safe for JSON
            risk_score_safe = float(risk_score)
            if np.isnan(risk_score_safe) or np.isinf(risk_score_safe):
                risk_score_safe = 0.5
            
            return jsonify({
                'icao24': icao24,
                'callsign': callsign,
                'risk_level': predicted_risk,
                'risk_score': risk_score_safe,
                'message': 'Install SHAP library for detailed explanations',
                'basic_factors': basic_factors
            }), 200
            
    except Exception as e:
        logger.error(f"Explanation error: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


# ============================================================================
# NEW ENDPOINTS - Professor Requirements #1 & #3
# ============================================================================

@app.route("/api/flights/<icao24>/future-risk", methods=["GET", "POST"])
@token_required
def get_future_risk(icao24):
    """
    Predict future risk evolution for a specific flight (Professor Requirement #3).
    
    Query parameters:
    - time_horizon: Number of future timesteps (default: 5)
    - time_step_seconds: Seconds between predictions (default: 60)
    
    OR
    
    - distance_km: Predict risk after traveling this distance
    - speed_kmh: Average speed (default: 800)
    
    Returns:
        {
            "success": true,
            "icao24": "...",
            "current_risk": 0.45,
            "future_positions": [...],
            "future_risk_scores": [0.45, 0.52, 0.61, ...],
            "future_risk_levels": ["MEDIUM", "MEDIUM", "HIGH", ...],
            "timestamps": [...],
            "risk_evolution": "increasing",
            "warnings": [...]
        }
    """
    logger.info(f"Future risk prediction request for {icao24}")
    
    try:
        # Get models (lazy load)
        models = get_models()
        if models is None:
            return jsonify({
                "error": "ML models not loaded",
                "details": "Please wait for models to initialize or train models first"
            }), 503
        
        # Get parameters
        time_horizon = int(request.args.get('time_horizon', 5))
        time_step_seconds = int(request.args.get('time_step_seconds', 60))
        distance_km = request.args.get('distance_km', None)
        speed_kmh = float(request.args.get('speed_kmh', 800))
        
        # Fetch current flight data
        bbox = DEFAULT_BBOX
        raw = fetch_flights(bbox=bbox)
        
        if raw.empty:
            return jsonify({"error": "No flights available"}), 404
        
        # Find specific flight
        flight_data = raw[raw['icao24'] == icao24]
        if flight_data.empty:
            return jsonify({"error": f"Flight {icao24} not found"}), 404
        
        # Build features
        featured = build_featured_flights(flight_data)
        
        # Prepare feature vector for risk prediction
        feature_cols = [
            'altitude', 'velocity', 'vertical_rate', 'heading',
            'speed_kmh', 'is_climbing', 'is_descending',
            'speed_variation', 'altitude_change_rate', 'heading_change_rate',
            'acceleration', 'temperature', 'wind_speed', 'visibility',
            'crosswind', 'headwind', 'severe_weather', 'low_visibility',
            'high_winds', 'icing_risk', 'time_since_last_update'
        ]
        available_cols = [col for col in feature_cols if col in featured.columns]
        current_features = featured[available_cols].fillna(0).iloc[0].values
        
        # Prepare trajectory sequence (we'll use simplified single-point extrapolation)
        # In production, this should use historical trajectory data
        current_point = np.array([
            featured['lat'].iloc[0],
            featured['lon'].iloc[0],
            featured['altitude'].iloc[0],
            featured['heading'].iloc[0]
        ])
        
        # Create a simple historical sequence (repeated current point as fallback)
        # In production, fetch actual historical trajectory
        sequence_length = 10
        current_sequence = np.tile(current_point, (sequence_length, 1))
        
        # Predict future risk
        if distance_km is not None:
            # Distance-based prediction
            distance_km = float(distance_km)
            result = models.predict_risk_at_distance(
                current_sequence, current_features,
                distance_km, speed_kmh
            )
        else:
            # Time-based prediction
            result = models.predict_future_risk(
                current_sequence, current_features,
                time_horizon, time_step_seconds
            )
        
        if result is None or not result.get('success', False):
            return jsonify({
                "error": "Future risk prediction failed",
                "details": result.get('error', 'Unknown error') if result else 'Model not available'
            }), 500
        
        # Transform result to match frontend expectations
        predictions = []
        for i in range(len(result.get('future_risk_scores', []))):
            predictions.append({
                'time_offset_seconds': (i + 1) * time_step_seconds,
                'risk_score': float(result['future_risk_scores'][i]),
                'risk_level': result['future_risk_levels'][i]
            })
        
        # Get current risk level from first prediction or classify current state
        current_risk_score = float(featured['risk_score'].iloc[0])
        if current_risk_score < 0.33:
            current_risk_level = 'LOW'
        elif current_risk_score < 0.66:
            current_risk_level = 'MEDIUM'
        else:
            current_risk_level = 'HIGH'
        
        response = {
            'success': True,
            'icao24': icao24,
            'callsign': featured['callsign'].iloc[0],
            'current_altitude': float(featured['altitude'].iloc[0]),
            'current_speed_kmh': float(featured['speed_kmh'].iloc[0]),
            'current_risk_level': current_risk_level,
            'current_risk_score': current_risk_score,
            'predictions': predictions,
            'risk_evolution': result.get('risk_evolution', 'unknown'),
            'warnings': result.get('warnings', []),
            'prediction_horizon_minutes': result.get('prediction_horizon_minutes', 5)
        }
        
        return jsonify(response), 200
        
    except Exception as e:
        logger.error(f"Future risk prediction error: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/thresholds/dynamic", methods=["GET"])
@token_required
def get_dynamic_thresholds():
    """
    Get dynamic risk thresholds based on context (Professor Requirement #1).
    
    Query parameters:
    - altitude: Altitude in meters (optional)
    - flight_phase: Flight phase (optional: takeoff, landing, cruise, climb, descent)
    - weather_condition: Weather condition (optional: clear, clouds, rain, thunderstorm, etc.)
    
    Returns:
        {
            "base_thresholds": {"low": 0.33, "high": 0.66},
            "dynamic_thresholds": {"low": 0.28, "high": 0.56},
            "adjustments": {
                "altitude_multiplier": 0.85,
                "phase_multiplier": 1.0,
                "weather_multiplier": 1.0
            },
            "context": {
                "altitude": 1500.0,
                "flight_phase": "landing",
                "weather_condition": "rain"
            }
        }
    """
    try:
        # Get models (lazy load)
        models = get_models()
        if models is None:
            return jsonify({
                "error": "ML models not loaded",
                "details": "Please wait for models to initialize"
            }), 503
        
        # Get parameters
        altitude = request.args.get('altitude', None)
        if altitude is not None:
            altitude = float(altitude)
        
        flight_phase = request.args.get('flight_phase', None)
        weather_condition = request.args.get('weather_condition', None)
        
        # Get dynamic thresholds
        low_thresh, high_thresh = models.get_dynamic_thresholds(
            altitude, flight_phase, weather_condition
        )
        
        # Get threshold manager info
        if models.threshold_manager:
            info = models.threshold_manager.get_threshold_info()
        else:
            info = {
                'base_thresholds': {'low': 0.33, 'high': 0.66},
                'adjustments_enabled': {
                    'phase': False,
                    'altitude': False,
                    'weather': False
                }
            }
        
        return jsonify({
            "base_thresholds": info['base_thresholds'],
            "dynamic_thresholds": {
                "low": float(low_thresh),
                "high": float(high_thresh)
            },
            "context": {
                "altitude": altitude,
                "flight_phase": flight_phase,
                "weather_condition": weather_condition
            },
            "configuration": info
        }), 200
        
    except Exception as e:
        logger.error(f"Dynamic threshold retrieval error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/flights/<icao24>/risk-classification", methods=["GET"])
@token_required
def get_dynamic_risk_classification(icao24):
    """
    Get risk classification using dynamic thresholds for a specific flight.
    
    Returns both fixed and dynamic threshold classifications for comparison.
    
    Returns:
        {
            "icao24": "...",
            "risk_score": 0.55,
            "fixed_thresholds": {
                "risk_level": "MEDIUM",
                "low_threshold": 0.33,
                "high_threshold": 0.66
            },
            "dynamic_thresholds": {
                "risk_level": "HIGH",
                "low_threshold": 0.26,
                "high_threshold": 0.53,
                "explanation": "Stricter thresholds due to landing phase + rain"
            }
        }
    """
    try:
        # Get models (lazy load)
        models = get_models()
        if models is None:
            return jsonify({
                "error": "ML models not loaded",
                "details": "Please wait for models to initialize"
            }), 503
        
        # Fetch flight data
        bbox = DEFAULT_BBOX
        raw = fetch_flights(bbox=bbox)
        
        if raw.empty:
            return jsonify({"error": "No flights available"}), 404
        
        # Find specific flight
        flight_data = raw[raw['icao24'] == icao24]
        if flight_data.empty:
            return jsonify({"error": f"Flight {icao24} not found"}), 404
        
        # Build features with FIXED thresholds
        featured_fixed = build_featured_flights(flight_data, use_dynamic_thresholds=False)
        
        # Get risk score
        risk_score = float(featured_fixed['risk_score'].iloc[0])
        fixed_risk_level = featured_fixed['risk_level'].iloc[0]
        
        # Get dynamic classification
        altitude = float(featured_fixed['altitude'].iloc[0])
        flight_phase = featured_fixed.get('flight_phase', pd.Series(['cruise'])).iloc[0]
        
        # Extract weather condition
        weather_condition = 'clear'
        if 'weather' in featured_fixed.columns:
            weather_data = featured_fixed['weather'].iloc[0]
            if isinstance(weather_data, dict):
                weather_condition = weather_data.get('condition', 'clear')
        
        # Get dynamic thresholds
        low_thresh, high_thresh = models.get_dynamic_thresholds(
            altitude, flight_phase, weather_condition
        )
        
        # Classify using dynamic thresholds
        dynamic_risk_level = models.classify_risk_dynamic(
            risk_score, altitude, flight_phase, weather_condition
        )
        
        return jsonify({
            "icao24": icao24,
            "callsign": featured_fixed['callsign'].iloc[0],
            "risk_score": risk_score,
            "context": {
                "altitude": altitude,
                "flight_phase": flight_phase,
                "weather_condition": weather_condition
            },
            "fixed_thresholds": {
                "risk_level": fixed_risk_level,
                "low_threshold": 0.33,
                "high_threshold": 0.66
            },
            "dynamic_thresholds": {
                "risk_level": dynamic_risk_level,
                "low_threshold": float(low_thresh),
                "high_threshold": float(high_thresh),
                "explanation": f"Adjusted thresholds based on {flight_phase} phase at {altitude:.0f}m with {weather_condition} conditions"
            },
            "threshold_difference": {
                "same_classification": fixed_risk_level == dynamic_risk_level,
                "adjustment_factor": float(low_thresh / 0.33)
            }
        }), 200
        
    except Exception as e:
        logger.error(f"Dynamic classification error: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    # Run dev server
    app.run(host="127.0.0.1", port=5000, debug=True)
