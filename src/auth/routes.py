"""
Authentication routes for user registration, login, and profile management.
"""
from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta
from sqlalchemy import func
import re
import secrets
from src.database.models import User, UserPreferences, EmailOTP, get_db, init_db
from src.auth.jwt_utils import create_access_token, token_required, admin_required, get_current_user
from src.email.email_service import EmailService

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')

# Initialize database on module load
init_db()

# Initialize email service
email_service = EmailService()


def generate_otp():
    """Generate a 6-digit OTP code."""
    return ''.join([str(secrets.randbelow(10)) for _ in range(6)])


def validate_email(email):
    """Validate email format."""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


def validate_password(password):
    """Validate password strength."""
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    if not re.search(r'[A-Z]', password):
        return False, "Password must contain at least one uppercase letter"
    if not re.search(r'[a-z]', password):
        return False, "Password must contain at least one lowercase letter"
    if not re.search(r'[0-9]', password):
        return False, "Password must contain at least one number"
    return True, "Valid"


@auth_bp.route('/register', methods=['POST'])
def register():
    """Register a new user (requires OTP verification)."""
    try:
        data = request.get_json()
        
        # Validate required fields
        email = data.get('email', '').strip().lower()
        username = data.get('username', '').strip()
        password = data.get('password', '')
        full_name = data.get('full_name', '').strip()
        
        if not all([email, username, password]):
            return jsonify({'error': 'Email, username, and password are required'}), 400
        
        # Validate email
        if not validate_email(email):
            return jsonify({'error': 'Invalid email format'}), 400
        
        # Validate password
        is_valid, message = validate_password(password)
        if not is_valid:
            return jsonify({'error': message}), 400
        
        # Check database
        db = next(get_db())
        
        # Verify that OTP has been verified for this email
        verified_otp = db.query(EmailOTP).filter(
            EmailOTP.email == email,
            EmailOTP.purpose == 'signup',
            EmailOTP.is_verified == True
        ).order_by(EmailOTP.verified_at.desc()).first()
        
        if not verified_otp:
            return jsonify({'error': 'Email not verified. Please verify your email with OTP first.'}), 403
        
        # Check if OTP verification is recent (within 30 minutes)
        if verified_otp.verified_at:
            time_since_verification = datetime.utcnow() - verified_otp.verified_at
            if time_since_verification > timedelta(minutes=30):
                return jsonify({'error': 'Email verification expired. Please verify your email again.'}), 403
        
        # Check if user already exists
        existing_user = db.query(User).filter(
            (User.email == email) | (User.username == username)
        ).first()
        
        if existing_user:
            if existing_user.email == email:
                return jsonify({'error': 'Email already registered'}), 409
            else:
                return jsonify({'error': 'Username already taken'}), 409
        
        # Create new user
        new_user = User(
            email=email,
            username=username,
            full_name=full_name,
            role='user',
            email_verified=True  # Mark as verified since OTP was verified
        )
        new_user.set_password(password)
        
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        
        # Delete used OTP
        db.delete(verified_otp)
        db.commit()
        
        # Create default preferences
        preferences = UserPreferences(user_id=new_user.id)
        db.add(preferences)
        db.commit()
        
        # Create access token
        token = create_access_token(data={
            'user_id': new_user.id,
            'email': new_user.email,
            'username': new_user.username,
            'role': new_user.role
        })
        
        return jsonify({
            'message': 'User registered successfully',
            'user': new_user.to_dict(),
            'token': token
        }), 201
        
    except Exception as e:
        return jsonify({'error': f'Registration failed: {str(e)}'}), 500


@auth_bp.route('/login', methods=['POST'])
def login():
    """Login user and return JWT token."""
    try:
        data = request.get_json()
        
        email_or_username = data.get('email', '').strip()
        password = data.get('password', '')
        
        if not email_or_username or not password:
            return jsonify({'error': 'Email/username and password are required'}), 400
        
        db = next(get_db())
        
        # Find user by email or username (case-insensitive)
        user = db.query(User).filter(
            (func.lower(User.email) == email_or_username.lower()) | 
            (func.lower(User.username) == email_or_username.lower())
        ).first()
        
        if not user:
            return jsonify({'error': 'Invalid credentials'}), 401
        
        # Check if deletion was requested
        if user.deletion_requested_at:
            # Check if still within 30-day grace period
            if datetime.utcnow() < user.deletion_scheduled_at:
                days_remaining = (user.deletion_scheduled_at - datetime.utcnow()).days
                return jsonify({
                    'error': 'account_deletion_pending',
                    'message': f'Your account deletion is scheduled. {days_remaining} days remaining.',
                    'deletion_scheduled_at': user.deletion_scheduled_at.isoformat(),
                    'days_remaining': days_remaining,
                    'can_cancel': True,
                    'info': 'You can cancel the deletion by confirming your login.'
                }), 403
            else:
                # Grace period expired, account should be deleted
                return jsonify({
                    'error': 'Account deletion period expired. Account scheduled for removal.'
                }), 410
        
        # Check if account is deactivated (not deletion-related)
        if not user.is_active and not user.deletion_requested_at:
            return jsonify({'error': 'Account is deactivated. Contact administrator.'}), 403
        
        # Verify password
        if not user.check_password(password):
            return jsonify({'error': 'Invalid credentials'}), 401
        
        # Update last login
        user.last_login = datetime.utcnow()
        db.commit()
        
        # Create access token
        token = create_access_token(data={
            'user_id': user.id,
            'email': user.email,
            'username': user.username,
            'role': user.role
        })
        
        return jsonify({
            'message': 'Login successful',
            'user': user.to_dict(),
            'token': token
        }), 200
        
    except Exception as e:
        return jsonify({'error': f'Login failed: {str(e)}'}), 500


@auth_bp.route('/me', methods=['GET'])
@token_required
def get_profile():
    """Get current user profile."""
    try:
        current_user = get_current_user()
        db = next(get_db())
        
        user = db.query(User).filter(User.id == current_user['user_id']).first()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        return jsonify({'user': user.to_dict()}), 200
        
    except Exception as e:
        return jsonify({'error': f'Failed to get profile: {str(e)}'}), 500


@auth_bp.route('/me', methods=['PUT'])
@token_required
def update_profile():
    """Update current user profile."""
    try:
        current_user = get_current_user()
        data = request.get_json()
        
        db = next(get_db())
        user = db.query(User).filter(User.id == current_user['user_id']).first()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Update allowed fields
        if 'full_name' in data:
            user.full_name = data['full_name'].strip()
        
        if 'email' in data:
            new_email = data['email'].strip().lower()
            if new_email != user.email:
                if not validate_email(new_email):
                    return jsonify({'error': 'Invalid email format'}), 400
                
                # Check if email already exists
                existing = db.query(User).filter(User.email == new_email).first()
                if existing:
                    return jsonify({'error': 'Email already in use'}), 409
                
                user.email = new_email
                user.email_verified = False  # Need to re-verify
        
        db.commit()
        db.refresh(user)
        
        return jsonify({
            'message': 'Profile updated successfully',
            'user': user.to_dict()
        }), 200
        
    except Exception as e:
        return jsonify({'error': f'Failed to update profile: {str(e)}'}), 500


@auth_bp.route('/change-password', methods=['POST'])
@token_required
def change_password():
    """Change user password."""
    try:
        current_user = get_current_user()
        data = request.get_json()
        
        old_password = data.get('old_password', '')
        new_password = data.get('new_password', '')
        
        if not old_password or not new_password:
            return jsonify({'error': 'Old and new passwords are required'}), 400
        
        # Validate new password
        is_valid, message = validate_password(new_password)
        if not is_valid:
            return jsonify({'error': message}), 400
        
        db = next(get_db())
        user = db.query(User).filter(User.id == current_user['user_id']).first()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Verify old password
        if not user.check_password(old_password):
            return jsonify({'error': 'Current password is incorrect'}), 401
        
        # Set new password
        user.set_password(new_password)
        db.commit()
        
        return jsonify({'message': 'Password changed successfully'}), 200
        
    except Exception as e:
        return jsonify({'error': f'Failed to change password: {str(e)}'}), 500


@auth_bp.route('/verify-token', methods=['GET'])
@token_required
def verify_token():
    """Verify if token is valid."""
    current_user = get_current_user()
    return jsonify({
        'valid': True,
        'user': current_user
    }), 200


@auth_bp.route('/send-otp', methods=['POST'])
def send_otp():
    """Send OTP to email for verification."""
    try:
        data = request.get_json()
        email = data.get('email', '').strip().lower()
        purpose = data.get('purpose', 'signup')
        
        if not email:
            return jsonify({'error': 'Email is required'}), 400
        
        # Validate email format
        if not validate_email(email):
            return jsonify({'error': 'Invalid email format'}), 400
        
        # Check if user already exists (for signup purpose)
        if purpose == 'signup':
            db = next(get_db())
            existing_user = db.query(User).filter(User.email == email).first()
            if existing_user:
                return jsonify({'error': 'Email already registered'}), 409
        
        # Generate OTP
        otp_code = generate_otp()
        expires_at = datetime.utcnow() + timedelta(minutes=10)
        
        # Save OTP to database
        db = next(get_db())
        
        # Delete any existing OTPs for this email
        db.query(EmailOTP).filter(
            EmailOTP.email == email,
            EmailOTP.purpose == purpose
        ).delete()
        
        # Create new OTP
        new_otp = EmailOTP(
            email=email,
            otp_code=otp_code,
            purpose=purpose,
            expires_at=expires_at
        )
        db.add(new_otp)
        db.commit()
        
        # Send OTP email
        email_sent = email_service.send_otp(email, otp_code, purpose)
        
        if not email_sent:
            return jsonify({'error': 'Failed to send OTP email. Please try again.'}), 500
        
        return jsonify({
            'message': 'OTP sent successfully',
            'expires_in_minutes': 10
        }), 200
        
    except Exception as e:
        return jsonify({'error': f'Failed to send OTP: {str(e)}'}), 500


@auth_bp.route('/verify-otp', methods=['POST'])
def verify_otp():
    """Verify OTP code."""
    try:
        data = request.get_json()
        email = data.get('email', '').strip().lower()
        otp_code = data.get('otp_code', '').strip()
        purpose = data.get('purpose', 'signup')
        
        if not email or not otp_code:
            return jsonify({'error': 'Email and OTP code are required'}), 400
        
        db = next(get_db())
        
        # Find the most recent OTP for this email
        otp = db.query(EmailOTP).filter(
            EmailOTP.email == email,
            EmailOTP.purpose == purpose
        ).order_by(EmailOTP.created_at.desc()).first()
        
        if not otp:
            return jsonify({'error': 'No OTP found for this email'}), 404
        
        # Check if OTP is expired
        if otp.is_expired():
            return jsonify({'error': 'OTP has expired. Please request a new one.'}), 400
        
        # Check if already verified
        if otp.is_verified:
            return jsonify({'error': 'OTP has already been used'}), 400
        
        # Check if max attempts exceeded
        if otp.attempts >= otp.max_attempts:
            return jsonify({'error': 'Maximum verification attempts exceeded. Please request a new OTP.'}), 400
        
        # Verify OTP
        if otp.verify(otp_code):
            db.commit()
            return jsonify({
                'message': 'OTP verified successfully',
                'verified': True
            }), 200
        else:
            db.commit()
            remaining_attempts = otp.max_attempts - otp.attempts
            return jsonify({
                'error': f'Invalid OTP code. {remaining_attempts} attempts remaining.',
                'remaining_attempts': remaining_attempts
            }), 400
        
    except Exception as e:
        return jsonify({'error': f'Failed to verify OTP: {str(e)}'}), 500


@auth_bp.route('/resend-otp', methods=['POST'])
def resend_otp():
    """Resend OTP to email."""
    return send_otp()  # Reuse send_otp logic
