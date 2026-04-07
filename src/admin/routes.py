"""
Admin dashboard routes for user management and system monitoring.
"""
from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta
from sqlalchemy import func
from src.database.models import User, AuditLog, SystemMetrics, Alert, Watchlist, get_db
from src.auth.jwt_utils import admin_required, get_current_user

admin_bp = Blueprint('admin', __name__, url_prefix='/api/admin')


@admin_bp.route('/users', methods=['GET'])
@admin_required
def get_users():
    """Get all users (admin only)."""
    try:
        db = next(get_db())
        
        # Query parameters
        page = int(request.args.get('page', 1))
        per_page = min(int(request.args.get('per_page', 20)), 100)
        search = request.args.get('search', '').strip()
        role_filter = request.args.get('role', '')
        active_only = request.args.get('active_only', 'false').lower() == 'true'
        
        # Build query
        query = db.query(User)
        
        if search:
            query = query.filter(
                (User.email.like(f'%{search}%')) |
                (User.username.like(f'%{search}%')) |
                (User.full_name.like(f'%{search}%'))
            )
        
        if role_filter:
            query = query.filter(User.role == role_filter)
        
        if active_only:
            query = query.filter(User.is_active == True)
        
        # Get total count
        total = query.count()
        
        # Paginate
        users = query.order_by(User.created_at.desc()).offset((page - 1) * per_page).limit(per_page).all()
        
        return jsonify({
            'users': [u.to_dict() for u in users],
            'total': total,
            'page': page,
            'per_page': per_page,
            'pages': (total + per_page - 1) // per_page
        }), 200
        
    except Exception as e:
        return jsonify({'error': f'Failed to get users: {str(e)}'}), 500


@admin_bp.route('/users/<int:user_id>', methods=['GET'])
@admin_required
def get_user_details(user_id):
    """Get detailed user information."""
    try:
        db = next(get_db())
        
        user = db.query(User).filter(User.id == user_id).first()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Get user stats
        watchlist_count = db.query(Watchlist).filter(Watchlist.user_id == user_id).count()
        alert_count = db.query(Alert).filter(Alert.user_id == user_id).count()
        unread_alerts = db.query(Alert).filter(
            Alert.user_id == user_id,
            Alert.is_read == False
        ).count()
        
        return jsonify({
            'user': user.to_dict(),
            'stats': {
                'watchlist_count': watchlist_count,
                'alert_count': alert_count,
                'unread_alerts': unread_alerts
            }
        }), 200
        
    except Exception as e:
        return jsonify({'error': f'Failed to get user details: {str(e)}'}), 500


@admin_bp.route('/users/<int:user_id>/activate', methods=['POST'])
@admin_required
def activate_user(user_id):
    """Activate a user account."""
    try:
        db = next(get_db())
        
        user = db.query(User).filter(User.id == user_id).first()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        user.is_active = True
        db.commit()
        
        return jsonify({'message': f'User {user.username} activated successfully'}), 200
        
    except Exception as e:
        return jsonify({'error': f'Failed to activate user: {str(e)}'}), 500


@admin_bp.route('/users/<int:user_id>/deactivate', methods=['POST'])
@admin_required
def deactivate_user(user_id):
    """Deactivate a user account."""
    try:
        current_user = get_current_user()
        
        # Prevent self-deactivation
        if user_id == current_user['user_id']:
            return jsonify({'error': 'Cannot deactivate your own account'}), 400
        
        db = next(get_db())
        
        user = db.query(User).filter(User.id == user_id).first()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        user.is_active = False
        db.commit()
        
        return jsonify({'message': f'User {user.username} deactivated successfully'}), 200
        
    except Exception as e:
        return jsonify({'error': f'Failed to deactivate user: {str(e)}'}), 500


@admin_bp.route('/users/<int:user_id>/role', methods=['PUT'])
@admin_required
def update_user_role(user_id):
    """Update user role (user/admin)."""
    try:
        current_user = get_current_user()
        data = request.get_json()
        
        new_role = data.get('role', '').lower()
        
        if new_role not in ['user', 'admin']:
            return jsonify({'error': 'Invalid role. Must be "user" or "admin"'}), 400
        
        # Prevent self-demotion
        if user_id == current_user['user_id'] and new_role != 'admin':
            return jsonify({'error': 'Cannot demote your own admin role'}), 400
        
        db = next(get_db())
        
        user = db.query(User).filter(User.id == user_id).first()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        user.role = new_role
        db.commit()
        
        return jsonify({'message': f'User role updated to {new_role}'}), 200
        
    except Exception as e:
        return jsonify({'error': f'Failed to update user role: {str(e)}'}), 500


@admin_bp.route('/dashboard/stats', methods=['GET'])
@admin_required
def get_dashboard_stats():
    """Get admin dashboard statistics."""
    try:
        db = next(get_db())
        
        # User statistics
        total_users = db.query(User).count()
        active_users = db.query(User).filter(User.is_active == True).count()
        admin_count = db.query(User).filter(User.role == 'admin').count()
        
        # New users in last 7 days
        week_ago = datetime.utcnow() - timedelta(days=7)
        new_users_week = db.query(User).filter(User.created_at >= week_ago).count()
        
        # Alert statistics
        total_alerts = db.query(Alert).count()
        unread_alerts = db.query(Alert).filter(Alert.is_read == False).count()
        
        # Watchlist statistics
        total_watchlists = db.query(Watchlist).count()
        active_watchlists = db.query(Watchlist).filter(Watchlist.is_active == True).count()
        
        # Recent audit logs (last 24 hours)
        day_ago = datetime.utcnow() - timedelta(days=1)
        recent_actions = db.query(AuditLog).filter(AuditLog.created_at >= day_ago).count()
        
        return jsonify({
            'users': {
                'total': total_users,
                'active': active_users,
                'admins': admin_count,
                'new_this_week': new_users_week
            },
            'alerts': {
                'total': total_alerts,
                'unread': unread_alerts
            },
            'watchlists': {
                'total': total_watchlists,
                'active': active_watchlists
            },
            'activity': {
                'actions_24h': recent_actions
            }
        }), 200
        
    except Exception as e:
        return jsonify({'error': f'Failed to get dashboard stats: {str(e)}'}), 500


@admin_bp.route('/audit-logs', methods=['GET'])
@admin_required
def get_audit_logs():
    """Get audit logs (limited to latest 100 entries)."""
    try:
        db = next(get_db())
        
        # Query parameters
        page = int(request.args.get('page', 1))
        per_page = min(int(request.args.get('per_page', 50)), 200)
        user_id = request.args.get('user_id', type=int)
        action = request.args.get('action', '')
        
        # Clean up old logs - keep only latest 100
        total_logs = db.query(AuditLog).count()
        if total_logs > 100:
            # Get the ID of the 100th most recent log
            cutoff_log = db.query(AuditLog).order_by(AuditLog.created_at.desc()).offset(100).limit(1).first()
            if cutoff_log:
                # Delete all logs older than the cutoff
                db.query(AuditLog).filter(AuditLog.created_at < cutoff_log.created_at).delete()
                db.commit()
        
        # Build query - get latest 100 logs
        subquery = db.query(AuditLog.id).order_by(AuditLog.created_at.desc()).limit(100).subquery()
        query = db.query(AuditLog).join(User, AuditLog.user_id == User.id, isouter=True).filter(AuditLog.id.in_(subquery))
        
        if user_id:
            query = query.filter(AuditLog.user_id == user_id)
        
        if action:
            query = query.filter(AuditLog.action.like(f'%{action}%'))
        
        # Get total (capped at 100)
        total = min(query.count(), 100)
        
        # Calculate total pages
        import math
        total_pages = math.ceil(total / per_page) if total > 0 else 1
        
        # Paginate
        logs = query.order_by(AuditLog.created_at.desc()).offset((page - 1) * per_page).limit(per_page).all()
        
        return jsonify({
            'logs': [{
                'id': log.id,
                'user_id': log.user_id,
                'username': log.user.username if log.user else 'Unknown',
                'action': log.action,
                'resource': log.resource,
                'details': log.details,
                'success': log.success,
                'ip_address': log.ip_address,
                'created_at': log.created_at.isoformat() if log.created_at else None
            } for log in logs],
            'total': total,
            'page': page,
            'per_page': per_page,
            'total_pages': total_pages
        }), 200
        
    except Exception as e:
        return jsonify({'error': f'Failed to get audit logs: {str(e)}'}), 500


@admin_bp.route('/system-metrics', methods=['GET'])
@admin_required
def get_system_metrics():
    """Get system performance metrics."""
    try:
        db = next(get_db())
        
        period = request.args.get('period', 'daily')
        
        # Get recent metrics
        day_ago = datetime.utcnow() - timedelta(days=1)
        
        metrics = db.query(SystemMetrics).filter(
            SystemMetrics.metric_date >= day_ago,
            SystemMetrics.period == period
        ).all()
        
        # Aggregate by endpoint
        endpoint_stats = {}
        for metric in metrics:
            if metric.api_endpoint not in endpoint_stats:
                endpoint_stats[metric.api_endpoint] = {
                    'request_count': 0,
                    'error_count': 0,
                    'avg_response_time': []
                }
            
            endpoint_stats[metric.api_endpoint]['request_count'] += metric.request_count
            endpoint_stats[metric.api_endpoint]['error_count'] += metric.error_count
            if metric.avg_response_time:
                endpoint_stats[metric.api_endpoint]['avg_response_time'].append(metric.avg_response_time)
        
        # Calculate averages
        for endpoint in endpoint_stats:
            times = endpoint_stats[endpoint]['avg_response_time']
            endpoint_stats[endpoint]['avg_response_time'] = sum(times) / len(times) if times else 0
        
        # ML and cache stats
        ml_total = sum(m.ml_prediction_count for m in metrics)
        ml_fallback = sum(m.ml_fallback_count for m in metrics)
        cache_hits = sum(m.cache_hit_count for m in metrics)
        cache_misses = sum(m.cache_miss_count for m in metrics)
        
        cache_hit_rate = (cache_hits / (cache_hits + cache_misses) * 100) if (cache_hits + cache_misses) > 0 else 0
        
        return jsonify({
            'endpoints': endpoint_stats,
            'ml': {
                'total_predictions': ml_total,
                'fallback_count': ml_fallback,
                'ml_success_rate': ((ml_total - ml_fallback) / ml_total * 100) if ml_total > 0 else 0
            },
            'cache': {
                'hits': cache_hits,
                'misses': cache_misses,
                'hit_rate': cache_hit_rate
            }
        }), 200
        
    except Exception as e:
        return jsonify({'error': f'Failed to get system metrics: {str(e)}'}), 500


@admin_bp.route('/export/users', methods=['GET'])
@admin_required
def export_users():
    """Export all users data (CSV format)."""
    try:
        from datetime import timedelta
        
        db = next(get_db())
        
        users = db.query(User).all()
        
        # Simple CSV format
        csv_data = "ID,Email,Username,Full Name,Role,Active,Created At (IST),Last Login (IST)\n"
        for user in users:
            csv_data += f"{user.id},{user.email},{user.username},{user.full_name or ''},"
            csv_data += f"{user.role},{user.is_active},"
            
            # Convert UTC to IST (UTC + 5:30)
            created_at_ist = ''
            if user.created_at:
                ist_time = user.created_at + timedelta(hours=5, minutes=30)
                created_at_ist = ist_time.strftime('%Y-%m-%d %H:%M:%S IST')
            
            last_login_ist = ''
            if user.last_login:
                ist_time = user.last_login + timedelta(hours=5, minutes=30)
                last_login_ist = ist_time.strftime('%Y-%m-%d %H:%M:%S IST')
            
            csv_data += f"{created_at_ist},{last_login_ist}\n"
        
        return csv_data, 200, {
            'Content-Type': 'text/csv',
            'Content-Disposition': 'attachment; filename=users_export.csv'
        }
        
    except Exception as e:
        return jsonify({'error': f'Failed to export users: {str(e)}'}), 500
