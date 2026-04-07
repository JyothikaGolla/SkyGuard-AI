"""
Database models for user authentication and management.
"""
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Float, Text, ForeignKey, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
import hashlib
import secrets

Base = declarative_base()


class User(Base):
    """User account model."""
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    salt = Column(String(64), nullable=False)
    
    # User profile
    full_name = Column(String(200))
    role = Column(String(20), default='user')  # 'user' or 'admin'
    is_active = Column(Boolean, default=True)
    email_verified = Column(Boolean, default=False)
    
    # Account deletion tracking
    deletion_requested_at = Column(DateTime, nullable=True)  # When user requested deletion
    deletion_scheduled_at = Column(DateTime, nullable=True)  # When account will be deleted (30 days after request)
    deactivation_reason = Column(Text, nullable=True)  # Optional reason for deactivation/deletion
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    preferences = relationship("UserPreferences", back_populates="user", uselist=False, cascade="all, delete-orphan")
    watchlists = relationship("Watchlist", back_populates="user", cascade="all, delete-orphan")
    alerts = relationship("Alert", back_populates="user", cascade="all, delete-orphan")
    analytics_history = relationship("AnalyticsHistory", back_populates="user", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="user", cascade="all, delete-orphan")
    
    def set_password(self, password):
        """Hash password with salt."""
        self.salt = secrets.token_hex(32)
        self.password_hash = hashlib.sha256((password + self.salt).encode()).hexdigest()
    
    def check_password(self, password):
        """Verify password."""
        return self.password_hash == hashlib.sha256((password + self.salt).encode()).hexdigest()
    
    def to_dict(self):
        """Convert to dictionary (exclude sensitive data)."""
        return {
            'id': self.id,
            'email': self.email,
            'username': self.username,
            'full_name': self.full_name,
            'role': self.role,
            'is_active': self.is_active,
            'email_verified': self.email_verified,
            'deletion_requested_at': self.deletion_requested_at.isoformat() if self.deletion_requested_at else None,
            'deletion_scheduled_at': self.deletion_scheduled_at.isoformat() if self.deletion_scheduled_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_login': self.last_login.isoformat() if self.last_login else None
        }


class UserPreferences(Base):
    """User preferences and settings."""
    __tablename__ = 'user_preferences'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), unique=True, nullable=False)
    
    # Alert settings
    email_alerts = Column(Boolean, default=True)
    risk_threshold = Column(String(10), default='MEDIUM')  # LOW, MEDIUM, HIGH
    alert_frequency = Column(String(20), default='immediate')  # immediate, hourly, daily
    
    # Default regions (JSON array)
    default_regions = Column(JSON, default=list)
    
    # Display preferences
    default_map_zoom = Column(Integer, default=5)
    default_map_center = Column(JSON, default={'lat': 20.5937, 'lng': 78.9629})
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="preferences")


class Watchlist(Base):
    """User's watched regions/flights."""
    __tablename__ = 'watchlists'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    
    name = Column(String(200), nullable=False)
    description = Column(Text)
    region_type = Column(String(50))  # 'bbox', 'country', 'custom'
    bbox = Column(String(100))  # "lat1,lat2,lon1,lon2"
    is_active = Column(Boolean, default=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="watchlists")


class Alert(Base):
    """Flight risk alerts for users."""
    __tablename__ = 'alerts'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    watchlist_id = Column(Integer, ForeignKey('watchlists.id'), nullable=True)
    
    alert_type = Column(String(50))  # 'high_risk', 'anomaly', 'weather_hazard'
    severity = Column(String(20))  # 'LOW', 'MEDIUM', 'HIGH'
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    
    # Flight details (JSON)
    flight_data = Column(JSON)
    
    # Status
    is_read = Column(Boolean, default=False)
    is_dismissed = Column(Boolean, default=False)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    read_at = Column(DateTime)
    
    # Relationships
    user = relationship("User", back_populates="alerts")


class AnalyticsHistory(Base):
    """Store user's analytics queries and results."""
    __tablename__ = 'analytics_history'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    
    query_type = Column(String(50))  # 'region', 'country', 'custom'
    query_params = Column(JSON)  # Store bbox, filters, etc.
    
    # Results summary
    total_flights = Column(Integer)
    high_risk_count = Column(Integer)
    anomaly_count = Column(Integer)
    
    # Full analytics data (JSON)
    analytics_data = Column(JSON)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="analytics_history")


class AuditLog(Base):
    """Audit log for tracking user actions."""
    __tablename__ = 'audit_logs'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    
    action = Column(String(100), nullable=False)  # 'login', 'fetch_flights', 'view_analytics', etc.
    resource = Column(String(100))  # What was accessed
    details = Column(JSON)  # Additional context
    ip_address = Column(String(45))
    user_agent = Column(String(500))
    
    # Status
    success = Column(Boolean, default=True)
    error_message = Column(Text)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="audit_logs")


class SystemMetrics(Base):
    """System-wide metrics for admin dashboard."""
    __tablename__ = 'system_metrics'
    
    id = Column(Integer, primary_key=True)
    
    # API usage
    api_endpoint = Column(String(100), nullable=False)
    request_count = Column(Integer, default=0)
    error_count = Column(Integer, default=0)
    avg_response_time = Column(Float)  # milliseconds
    
    # ML model performance
    ml_prediction_count = Column(Integer, default=0)
    ml_fallback_count = Column(Integer, default=0)
    
    # Cache statistics
    cache_hit_count = Column(Integer, default=0)
    cache_miss_count = Column(Integer, default=0)
    
    # Time period
    metric_date = Column(DateTime, default=datetime.utcnow)
    period = Column(String(20), default='hourly')  # hourly, daily, monthly
    
    created_at = Column(DateTime, default=datetime.utcnow)


class EmailOTP(Base):
    """Email OTP verification model."""
    __tablename__ = 'email_otps'
    
    id = Column(Integer, primary_key=True)
    email = Column(String(255), nullable=False, index=True)
    otp_code = Column(String(6), nullable=False)
    purpose = Column(String(50), default='signup')  # signup, password_reset, etc.
    
    # Verification tracking
    is_verified = Column(Boolean, default=False)
    attempts = Column(Integer, default=0)
    max_attempts = Column(Integer, default=5)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    verified_at = Column(DateTime)
    
    def is_expired(self):
        """Check if OTP has expired."""
        return datetime.utcnow() > self.expires_at
    
    def is_valid(self):
        """Check if OTP is still valid."""
        return not self.is_verified and not self.is_expired() and self.attempts < self.max_attempts
    
    def verify(self, code):
        """Verify OTP code."""
        self.attempts += 1
        if self.otp_code == code and self.is_valid():
            self.is_verified = True
            self.verified_at = datetime.utcnow()
            return True
        return False


# Database connection and session management
engine = None
SessionLocal = None


def init_db(database_url='sqlite:///flight_risk_ai.db'):
    """Initialize database connection and create tables."""
    global engine, SessionLocal
    
    # SQLite-specific settings for better connection handling
    engine = create_engine(
        database_url, 
        echo=False,
        connect_args={'check_same_thread': False},  # Allow multi-threading
        pool_pre_ping=True,  # Verify connections before using
        pool_size=10,  # Increase pool size
        max_overflow=20  # Allow overflow connections
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    # Create all tables
    Base.metadata.create_all(bind=engine)
    print(f"✅ Database initialized: {database_url}")
    
    return engine, SessionLocal


def get_db():
    """Get database session."""
    if SessionLocal is None:
        init_db()
    
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
