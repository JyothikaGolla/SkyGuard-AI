"""
Account Cleanup Script
Permanently deletes user accounts that have passed their 30-day grace period.

Run this script daily via:
- Windows: Task Scheduler
- Linux/Mac: crontab -e -> 0 2 * * * cd /path/to/project && python cleanup_expired_accounts.py
"""

import os
import sys
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database.models import User, EmailOTP, UserPreferences

# Database URL
DATABASE_URL = 'sqlite:///flight_risk_ai.db'


def cleanup_expired_accounts():
    """Delete users whose deletion grace period has expired"""
    
    # Create database connection
    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        # Find users whose deletion is scheduled and the time has passed
        now = datetime.utcnow()
        expired_users = session.query(User).filter(
            User.deletion_scheduled_at != None,
            User.deletion_scheduled_at <= now
        ).all()
        
        if not expired_users:
            print(f"[{now.isoformat()}] No accounts to delete.")
            return
        
        deleted_count = 0
        for user in expired_users:
            try:
                user_id = user.id
                user_email = user.email
                scheduled_at = user.deletion_scheduled_at
                
                # Delete associated data
                # 1. Email OTP records
                session.query(EmailOTP).filter(EmailOTP.user_id == user_id).delete()
                
                # 2. User preferences
                session.query(UserPreferences).filter(UserPreferences.user_id == user_id).delete()
                
                # 3. Delete the user
                session.delete(user)
                session.commit()
                
                deleted_count += 1
                print(f"[{now.isoformat()}] Deleted account: {user_email} (ID: {user_id}) - Scheduled: {scheduled_at}")
                
            except Exception as e:
                session.rollback()
                print(f"[{now.isoformat()}] ERROR deleting user {user.email}: {e}")
                continue
        
        print(f"[{now.isoformat()}] Cleanup completed. Deleted {deleted_count} account(s).")
        
    except Exception as e:
        print(f"[{now.isoformat()}] FATAL ERROR: {e}")
        session.rollback()
    finally:
        session.close()


if __name__ == '__main__':
    print("=" * 60)
    print("Account Cleanup Script - Starting")
    print("=" * 60)
    cleanup_expired_accounts()
    print("=" * 60)
    print("Account Cleanup Script - Finished")
    print("=" * 60)
