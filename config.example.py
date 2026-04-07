# Configuration file for Flight Risk AI
# Copy this to config.py and customize as needed

# API Configuration
API_HOST = "127.0.0.1"
API_PORT = 5000
DEBUG_MODE = True

# OpenSky Network Configuration
DEFAULT_BBOX = (6, 38, 68, 98)  # India: (min_lat, max_lat, min_lon, max_lon)
OPENSKY_TIMEOUT = 15  # seconds

# Alternative bounding boxes
BBOX_USA_EAST = (25, 50, -100, -65)
BBOX_EUROPE = (35, 70, -15, 40)
BBOX_JAPAN = (30, 45, 125, 150)
BBOX_AUSTRALIA = (-45, -10, 110, 160)

# ML Model Configuration
MODELS_DIR = "models"
USE_ML_BY_DEFAULT = True
LOAD_MODELS_ON_STARTUP = True

# Model Hyperparameters
LSTM_SEQUENCE_LENGTH = 10
LSTM_ENCODING_DIM = 32
LSTM_EPOCHS = 50

RISK_PREDICTOR_N_ESTIMATORS = 200
RISK_PREDICTOR_MAX_DEPTH = 6

ISOLATION_FOREST_CONTAMINATION = 0.1
ISOLATION_FOREST_N_ESTIMATORS = 100

CLUSTERER_N_CLUSTERS = 5
CLUSTERER_PCA_COMPONENTS = 10

# Feature Engineering
FEATURE_COLUMNS = [
    'altitude', 'velocity', 'vertical_rate', 'heading',
    'speed_kmh', 'is_climbing', 'is_descending', 'altitude_bin',
    'speed_variation', 'altitude_change_rate', 'heading_change_rate',
    'acceleration', 'time_since_last_update'
]

# Risk Thresholds
RISK_LOW_THRESHOLD = 0.33
RISK_HIGH_THRESHOLD = 0.66

# Training Data Generation
SYNTHETIC_DATA_N_SAMPLES = 20000
SYNTHETIC_DATA_N_FLIGHTS = 200
SYNTHETIC_DATA_RISK_PERCENTAGE = 0.05  # 5% risky flights

# Frontend Configuration
FRONTEND_MAP_CENTER = [20.5937, 78.9629]  # India center
FRONTEND_MAP_ZOOM = 5
FRONTEND_UPDATE_INTERVAL = 30000  # milliseconds (30 seconds)

# Logging
LOG_LEVEL = "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
