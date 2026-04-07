"""
Database Migration Script
Adds new columns for account deletion tracking and email OTP verification.
Run this once to update your existing database schema.
"""
import sqlite3
import os

DATABASE_URL = 'sqlite:///flight_risk_ai.db'

def migrate_database():
    """Add new columns to existing database tables."""
    
    # Extract database path from DATABASE_URL
    db_path = DATABASE_URL.replace('sqlite:///', '')
    
    if not os.path.exists(db_path):
        print(f"Database not found at: {db_path}")
        print("Creating new database with init_db()...")
        from src.database.models import init_db
        init_db()
        print("✓ New database created successfully")
        return
    
    print(f"Migrating database at: {db_path}")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check if users table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        if not cursor.fetchone():
            print("Users table not found. Initializing database...")
            conn.close()
            from src.database.models import init_db
            init_db()
            print("✓ Database initialized successfully")
            return
        
        # Get existing columns in users table
        cursor.execute("PRAGMA table_info(users)")
        existing_columns = {row[1] for row in cursor.fetchall()}
        
        print(f"Existing columns in users table: {existing_columns}")
        
        # Add deletion tracking columns if they don't exist
        migrations_needed = []
        
        if 'deletion_requested_at' not in existing_columns:
            migrations_needed.append(
                "ALTER TABLE users ADD COLUMN deletion_requested_at DATETIME"
            )
        
        if 'deletion_scheduled_at' not in existing_columns:
            migrations_needed.append(
                "ALTER TABLE users ADD COLUMN deletion_scheduled_at DATETIME"
            )
        
        if 'deactivation_reason' not in existing_columns:
            migrations_needed.append(
                "ALTER TABLE users ADD COLUMN deactivation_reason TEXT"
            )
        
        # Execute migrations
        if migrations_needed:
            print(f"\nApplying {len(migrations_needed)} migrations to users table...")
            for migration in migrations_needed:
                print(f"  - {migration.split('ADD COLUMN')[1].strip()}")
                cursor.execute(migration)
            conn.commit()
            print("✓ Users table migrations completed")
        else:
            print("✓ Users table is up to date")
        
        # Check if email_otp table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='email_otp'")
        if not cursor.fetchone():
            print("\nCreating email_otp table...")
            cursor.execute("""
                CREATE TABLE email_otp (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    email VARCHAR(255) NOT NULL,
                    otp_code VARCHAR(10) NOT NULL,
                    purpose VARCHAR(50) DEFAULT 'signup',
                    attempt_count INTEGER DEFAULT 0,
                    is_verified BOOLEAN DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    verified_at DATETIME,
                    expires_at DATETIME NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )
            """)
            cursor.execute("CREATE INDEX idx_email_otp_email ON email_otp(email)")
            cursor.execute("CREATE INDEX idx_email_otp_code ON email_otp(otp_code)")
            conn.commit()
            print("✓ email_otp table created successfully")
        else:
            print("\n✓ email_otp table already exists")
        
        print("\n" + "="*60)
        print("✅ Database migration completed successfully!")
        print("="*60)
        
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    print("="*60)
    print("Database Migration Script")
    print("="*60)
    migrate_database()
