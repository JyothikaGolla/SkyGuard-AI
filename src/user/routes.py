"""
User preferences and watchlist management routes.
"""
from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta
from src.database.models import User, UserPreferences, Watchlist, Alert, AnalyticsHistory, get_db
from src.auth.jwt_utils import token_required, get_current_user

user_bp = Blueprint('user', __name__, url_prefix='/api/user')


@user_bp.route('/preferences', methods=['GET'])
@token_required
def get_preferences():
    """Get user preferences."""
    try:
        current_user = get_current_user()
        db = next(get_db())
        
        prefs = db.query(UserPreferences).filter(UserPreferences.user_id == current_user['user_id']).first()
        
        if not prefs:
            # Create default preferences if not exists
            prefs = UserPreferences(user_id=current_user['user_id'])
            db.add(prefs)
            db.commit()
            db.refresh(prefs)
        
        return jsonify({
            'preferences': {
                'email_alerts': prefs.email_alerts,
                'risk_threshold': prefs.risk_threshold,
                'alert_frequency': prefs.alert_frequency,
                'default_regions': prefs.default_regions or [],
                'default_map_zoom': prefs.default_map_zoom,
                'default_map_center': prefs.default_map_center
            }
        }), 200
        
    except Exception as e:
        return jsonify({'error': f'Failed to get preferences: {str(e)}'}), 500


@user_bp.route('/preferences', methods=['PUT'])
@token_required
def update_preferences():
    """Update user preferences."""
    try:
        current_user = get_current_user()
        data = request.get_json()
        
        db = next(get_db())
        prefs = db.query(UserPreferences).filter(UserPreferences.user_id == current_user['user_id']).first()
        
        if not prefs:
            prefs = UserPreferences(user_id=current_user['user_id'])
            db.add(prefs)
        
        # Update fields
        if 'email_alerts' in data:
            prefs.email_alerts = bool(data['email_alerts'])
        if 'risk_threshold' in data:
            if data['risk_threshold'] in ['LOW', 'MEDIUM', 'HIGH']:
                prefs.risk_threshold = data['risk_threshold']
        if 'alert_frequency' in data:
            if data['alert_frequency'] in ['immediate', 'hourly', 'daily']:
                prefs.alert_frequency = data['alert_frequency']
        if 'default_regions' in data:
            prefs.default_regions = data['default_regions']
        if 'default_map_zoom' in data:
            prefs.default_map_zoom = int(data['default_map_zoom'])
        if 'default_map_center' in data:
            prefs.default_map_center = data['default_map_center']
        
        db.commit()
        
        return jsonify({'message': 'Preferences updated successfully'}), 200
        
    except Exception as e:
        return jsonify({'error': f'Failed to update preferences: {str(e)}'}), 500


@user_bp.route('/watchlists', methods=['GET'])
@token_required
def get_watchlists():
    """Get user's watchlists."""
    try:
        current_user = get_current_user()
        db = next(get_db())
        
        watchlists = db.query(Watchlist).filter(Watchlist.user_id == current_user['user_id']).all()
        
        return jsonify({
            'watchlists': [{
                'id': w.id,
                'name': w.name,
                'description': w.description,
                'region_type': w.region_type,
                'bbox': w.bbox,
                'is_active': w.is_active,
                'created_at': w.created_at.isoformat() if w.created_at else None
            } for w in watchlists]
        }), 200
        
    except Exception as e:
        return jsonify({'error': f'Failed to get watchlists: {str(e)}'}), 500


@user_bp.route('/watchlists', methods=['POST'])
@token_required
def create_watchlist():
    """Create a new watchlist."""
    try:
        current_user = get_current_user()
        data = request.get_json()
        
        name = data.get('name', '').strip()
        if not name:
            return jsonify({'error': 'Watchlist name is required'}), 400
        
        db = next(get_db())
        
        watchlist = Watchlist(
            user_id=current_user['user_id'],
            name=name,
            description=data.get('description', ''),
            region_type=data.get('region_type', 'bbox'),
            bbox=data.get('bbox', ''),
            is_active=True
        )
        
        db.add(watchlist)
        db.commit()
        db.refresh(watchlist)
        
        return jsonify({
            'message': 'Watchlist created successfully',
            'watchlist': {
                'id': watchlist.id,
                'name': watchlist.name,
                'description': watchlist.description,
                'region_type': watchlist.region_type,
                'bbox': watchlist.bbox,
                'is_active': watchlist.is_active
            }
        }), 201
        
    except Exception as e:
        return jsonify({'error': f'Failed to create watchlist: {str(e)}'}), 500


@user_bp.route('/watchlists/<int:watchlist_id>', methods=['PUT'])
@token_required
def update_watchlist(watchlist_id):
    """Update a watchlist."""
    try:
        current_user = get_current_user()
        data = request.get_json()
        
        db = next(get_db())
        watchlist = db.query(Watchlist).filter(
            Watchlist.id == watchlist_id,
            Watchlist.user_id == current_user['user_id']
        ).first()
        
        if not watchlist:
            return jsonify({'error': 'Watchlist not found'}), 404
        
        # Update fields
        if 'name' in data:
            watchlist.name = data['name'].strip()
        if 'description' in data:
            watchlist.description = data['description']
        if 'bbox' in data:
            watchlist.bbox = data['bbox']
        if 'is_active' in data:
            watchlist.is_active = bool(data['is_active'])
        
        db.commit()
        
        return jsonify({'message': 'Watchlist updated successfully'}), 200
        
    except Exception as e:
        return jsonify({'error': f'Failed to update watchlist: {str(e)}'}), 500


@user_bp.route('/watchlists/<int:watchlist_id>', methods=['DELETE'])
@token_required
def delete_watchlist(watchlist_id):
    """Delete a watchlist."""
    try:
        current_user = get_current_user()
        db = next(get_db())
        
        watchlist = db.query(Watchlist).filter(
            Watchlist.id == watchlist_id,
            Watchlist.user_id == current_user['user_id']
        ).first()
        
        if not watchlist:
            return jsonify({'error': 'Watchlist not found'}), 404
        
        db.delete(watchlist)
        db.commit()
        
        return jsonify({'message': 'Watchlist deleted successfully'}), 200
        
    except Exception as e:
        return jsonify({'error': f'Failed to delete watchlist: {str(e)}'}), 500


@user_bp.route('/alerts', methods=['GET'])
@token_required
def get_alerts():
    """Get user's alerts."""
    try:
        current_user = get_current_user()
        db = next(get_db())
        
        # Query parameters
        unread_only = request.args.get('unread_only', 'false').lower() == 'true'
        limit = min(int(request.args.get('limit', 50)), 100)
        
        query = db.query(Alert).filter(Alert.user_id == current_user['user_id'])
        
        if unread_only:
            query = query.filter(Alert.is_read == False)
        
        alerts = query.order_by(Alert.created_at.desc()).limit(limit).all()
        
        return jsonify({
            'alerts': [{
                'id': a.id,
                'alert_type': a.alert_type,
                'severity': a.severity,
                'title': a.title,
                'message': a.message,
                'flight_data': a.flight_data,
                'is_read': a.is_read,
                'created_at': a.created_at.isoformat() if a.created_at else None
            } for a in alerts],
            'total': len(alerts),
            'unread_count': db.query(Alert).filter(
                Alert.user_id == current_user['user_id'],
                Alert.is_read == False
            ).count()
        }), 200
        
    except Exception as e:
        return jsonify({'error': f'Failed to get alerts: {str(e)}'}), 500


@user_bp.route('/alerts/<int:alert_id>/read', methods=['POST'])
@token_required
def mark_alert_read(alert_id):
    """Mark alert as read."""
    try:
        current_user = get_current_user()
        db = next(get_db())
        
        alert = db.query(Alert).filter(
            Alert.id == alert_id,
            Alert.user_id == current_user['user_id']
        ).first()
        
        if not alert:
            return jsonify({'error': 'Alert not found'}), 404
        
        alert.is_read = True
        alert.read_at = datetime.utcnow()
        db.commit()
        
        return jsonify({'message': 'Alert marked as read'}), 200
        
    except Exception as e:
        return jsonify({'error': f'Failed to mark alert as read: {str(e)}'}), 500


@user_bp.route('/analytics-history', methods=['GET'])
@token_required
def get_analytics_history():
    """Get user's analytics query history."""
    try:
        current_user = get_current_user()
        db = next(get_db())
        
        limit = min(int(request.args.get('limit', 20)), 50)
        
        history = db.query(AnalyticsHistory).filter(
            AnalyticsHistory.user_id == current_user['user_id']
        ).order_by(AnalyticsHistory.created_at.desc()).limit(limit).all()
        
        return jsonify({
            'history': [{
                'id': h.id,
                'query_type': h.query_type,
                'query_params': h.query_params,
                'total_flights': h.total_flights,
                'high_risk_count': h.high_risk_count,
                'anomaly_count': h.anomaly_count,
                'created_at': h.created_at.isoformat() if h.created_at else None
            } for h in history]
        }), 200
        
    except Exception as e:
        return jsonify({'error': f'Failed to get analytics history: {str(e)}'}), 500


@user_bp.route('/analytics-history', methods=['POST'])
@token_required
def save_analytics_query():
    """Save an analytics query to history."""
    try:
        current_user = get_current_user()
        data = request.get_json()
        
        db = next(get_db())
        
        history = AnalyticsHistory(
            user_id=current_user['user_id'],
            query_type=data.get('query_type', 'custom'),
            query_params=data.get('query_params', {}),
            total_flights=data.get('total_flights', 0),
            high_risk_count=data.get('high_risk_count', 0),
            anomaly_count=data.get('anomaly_count', 0),
            analytics_data=data.get('analytics_data', {})
        )
        
        db.add(history)
        db.commit()
        
        return jsonify({'message': 'Analytics query saved to history'}), 201
        
    except Exception as e:
        return jsonify({'error': f'Failed to save analytics history: {str(e)}'}), 500


# ============================================================================
# ACCOUNT MANAGEMENT ENDPOINTS
# ============================================================================

@user_bp.route('/account/deactivate', methods=['POST'])
@token_required
def deactivate_account():
    """Temporarily deactivate account (can be reactivated)."""
    try:
        current_user = get_current_user()
        data = request.get_json()
        
        password = data.get('password', '')
        reason = data.get('reason', '')
        
        if not password:
            return jsonify({'error': 'Password confirmation required'}), 400
        
        db = next(get_db())
        user = db.query(User).filter(User.id == current_user['user_id']).first()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Verify password
        if not user.check_password(password):
            return jsonify({'error': 'Incorrect password'}), 401
        
        # Deactivate account
        user.is_active = False
        user.deactivation_reason = reason if reason else 'User requested deactivation'
        user.updated_at = datetime.utcnow()
        
        db.commit()
        
        return jsonify({
            'message': 'Account deactivated successfully',
            'info': 'Contact administrator to reactivate your account'
        }), 200
        
    except Exception as e:
        return jsonify({'error': f'Failed to deactivate account: {str(e)}'}), 500


@user_bp.route('/account/request-deletion', methods=['POST'])
@token_required
def request_deletion():
    """Request permanent account deletion (30-day grace period)."""
    try:
        current_user = get_current_user()
        data = request.get_json()
        
        password = data.get('password', '')
        reason = data.get('reason', '')
        
        if not password:
            return jsonify({'error': 'Password confirmation required'}), 400
        
        db = next(get_db())
        user = db.query(User).filter(User.id == current_user['user_id']).first()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Verify password
        if not user.check_password(password):
            return jsonify({'error': 'Incorrect password'}), 401
        
        # Check if deletion already requested
        if user.deletion_requested_at:
            days_remaining = (user.deletion_scheduled_at - datetime.utcnow()).days
            return jsonify({
                'error': 'Deletion already requested',
                'deletion_scheduled_at': user.deletion_scheduled_at.isoformat(),
                'days_remaining': days_remaining
            }), 409
        
        # Schedule deletion for 30 days from now
        now = datetime.utcnow()
        deletion_date = now + timedelta(days=30)
        
        user.deletion_requested_at = now
        user.deletion_scheduled_at = deletion_date
        user.is_active = False  # Deactivate immediately
        user.deactivation_reason = reason if reason else 'User requested deletion'
        user.updated_at = now
        
        db.commit()
        
        return jsonify({
            'message': 'Account deletion scheduled',
            'deletion_scheduled_at': deletion_date.isoformat(),
            'days_remaining': 30,
            'info': 'You have 30 days to cancel this request by logging back in. After 30 days, your account and all data will be permanently deleted.'
        }), 200
        
    except Exception as e:
        return jsonify({'error': f'Failed to request deletion: {str(e)}'}), 500


@user_bp.route('/account/cancel-deletion', methods=['POST'])
@token_required
def cancel_deletion():
    """Cancel pending account deletion and reactivate account."""
    try:
        current_user = get_current_user()
        
        db = next(get_db())
        user = db.query(User).filter(User.id == current_user['user_id']).first()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Check if deletion was requested
        if not user.deletion_requested_at:
            return jsonify({'error': 'No deletion request found'}), 404
        
        # Check if still within 30-day grace period
        if datetime.utcnow() > user.deletion_scheduled_at:
            return jsonify({
                'error': 'Deletion grace period has expired. Account cannot be recovered.'
            }), 410
        
        # Cancel deletion and reactivate
        user.deletion_requested_at = None
        user.deletion_scheduled_at = None
        user.is_active = True
        user.deactivation_reason = None
        user.updated_at = datetime.utcnow()
        
        db.commit()
        
        return jsonify({
            'message': 'Account deletion cancelled successfully',
            'info': 'Your account has been reactivated'
        }), 200
        
    except Exception as e:
        return jsonify({'error': f'Failed to cancel deletion: {str(e)}'}), 500


@user_bp.route('/account/status', methods=['GET'])
@token_required
def get_account_status():
    """Get current account status including deletion info."""
    try:
        current_user = get_current_user()
        
        db = next(get_db())
        user = db.query(User).filter(User.id == current_user['user_id']).first()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        status = {
            'is_active': user.is_active,
            'email_verified': user.email_verified,
            'deletion_requested': user.deletion_requested_at is not None,
            'deletion_requested_at': user.deletion_requested_at.isoformat() if user.deletion_requested_at else None,
            'deletion_scheduled_at': user.deletion_scheduled_at.isoformat() if user.deletion_scheduled_at else None,
            'deactivation_reason': user.deactivation_reason
        }
        
        # Calculate days remaining if deletion is scheduled
        if user.deletion_scheduled_at:
            days_remaining = (user.deletion_scheduled_at - datetime.utcnow()).days
            status['days_until_deletion'] = max(0, days_remaining)
        
        return jsonify(status), 200
        
    except Exception as e:
        return jsonify({'error': f'Failed to get account status: {str(e)}'}), 500
