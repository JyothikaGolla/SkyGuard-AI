"""
SkyGuard AI - Initialization and Setup Script

This script initializes the database, creates tables, and optionally creates an admin user.
Run this script before starting the application for the first time.
"""

import sys
import os
import secrets
from getpass import getpass

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from src.database.models import init_db, User, UserPreferences
from dotenv import load_dotenv

def check_env_file():
    """Check if .env file exists and has required variables."""
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    
    if not os.path.exists(env_path):
        print("⚠️  .env file not found!")
        print("Creating .env file from template...")
        
        template_path = os.path.join(os.path.dirname(__file__), '.env.template')
        if os.path.exists(template_path):
            with open(template_path, 'r') as template:
                content = template.read()
            
            # Generate secure JWT secret
            jwt_secret = secrets.token_urlsafe(32)
            content = content.replace(
                'your-super-secret-jwt-key-change-this-in-production-use-random-string',
                jwt_secret
            )
            
            with open(env_path, 'w') as env_file:
                env_file.write(content)
            
            print("✅ .env file created with secure JWT secret!")
            print(f"   JWT_SECRET_KEY: {jwt_secret}")
        else:
            print("❌ .env.template not found. Please create .env manually.")
            return False
    
    # Load and validate environment variables
    load_dotenv()
    
    jwt_secret = os.environ.get('JWT_SECRET_KEY')
    if not jwt_secret or jwt_secret == 'your-super-secret-jwt-key-change-this-in-production-use-random-string':
        print("⚠️  JWT_SECRET_KEY not set or using default value!")
        print("Please update your .env file with a secure JWT secret.")
        return False
    
    print("✅ Environment variables loaded successfully!")
    return True

def initialize_database():
    """Initialize database and create tables."""
    print("\n📊 Initializing database...")
    
    try:
        engine, SessionLocal = init_db()
        print("✅ Database initialized successfully!")
        print(f"   Database file: flight_risk_ai.db")
        return engine, SessionLocal
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
        return None, None

def create_admin_user(SessionLocal):
    """Create the first admin user."""
    print("\n👤 Admin User Setup")
    print("=" * 50)
    
    db = SessionLocal()
    
    try:
        # Check if any admin users exist
        existing_admin = db.query(User).filter(User.role == 'admin').first()
        if existing_admin:
            print(f"⚠️  Admin user already exists: {existing_admin.email}")
            create_another = input("Create another admin user? (y/n): ").lower().strip()
            if create_another != 'y':
                return
        
        # Get user details
        print("\nEnter admin user details:")
        full_name = input("Full Name: ").strip()
        username = input("Username: ").strip()
        email = input("Email: ").strip()
        
        # Check if email already exists
        existing_user = db.query(User).filter(User.email == email).first()
        if existing_user:
            print(f"❌ User with email {email} already exists!")
            return
        
        # Get password
        while True:
            password = getpass("Password (min 8 characters): ")
            confirm_password = getpass("Confirm Password: ")
            
            if password != confirm_password:
                print("❌ Passwords do not match. Try again.")
                continue
            
            if len(password) < 8:
                print("❌ Password must be at least 8 characters long.")
                continue
            
            break
        
        # Create admin user
        admin_user = User(
            email=email,
            username=username,
            full_name=full_name,
            role='admin',
            is_active=True,
            email_verified=True
        )
        admin_user.set_password(password)
        
        db.add(admin_user)
        db.commit()
        db.refresh(admin_user)
        
        # Create default preferences
        preferences = UserPreferences(
            user_id=admin_user.id,
            email_alerts=True,
            risk_threshold='MEDIUM',
            alert_frequency='immediate',
            default_regions=['india']
        )
        db.add(preferences)
        db.commit()
        
        print("\n✅ Admin user created successfully!")
        print(f"   Email: {email}")
        print(f"   Username: {username}")
        print(f"   Role: admin")
        print("\n🔐 You can now login at: http://127.0.0.1:5500/login.html")
        
    except Exception as e:
        print(f"❌ Failed to create admin user: {e}")
        db.rollback()
    finally:
        db.close()

def main():
    """Main initialization flow."""
    print("=" * 70)
    print("🚀 SkyGuard AI - Initialization Script")
    print("=" * 70)
    
    # Step 1: Check environment variables
    if not check_env_file():
        print("\n❌ Setup failed. Please fix the issues above and run again.")
        return
    
    # Step 2: Initialize database
    engine, SessionLocal = initialize_database()
    if not engine or not SessionLocal:
        print("\n❌ Setup failed. Database initialization error.")
        return
    
    # Step 3: Create admin user
    create_admin = input("\nCreate admin user? (y/n): ").lower().strip()
    if create_admin == 'y':
        create_admin_user(SessionLocal)
    
    # Summary
    print("\n" + "=" * 70)
    print("✅ Setup Complete!")
    print("=" * 70)
    print("\n📝 Next Steps:")
    print("1. Start the backend: python src/serving/api.py")
    print("2. Start the frontend: cd frontend && python -m http.server 5500")
    print("3. Open your browser: http://127.0.0.1:5500/login.html")
    print("\n📚 Documentation: See AUTH_SETUP_GUIDE.md for more details")
    print("=" * 70)

if __name__ == "__main__":
    main()
