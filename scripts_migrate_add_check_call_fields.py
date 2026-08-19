# scripts/migrate_add_check_call_fields.py

"""
Database migration script to add Check Call support fields.

This script safely adds new columns to the users table:
- sms_check_id (String, nullable)
- is_privacy_accepted (Boolean, default False)
- is_subscribed (Boolean, default False)

The migration is safe for existing
- All new columns are nullable or have default values
- Existing user records are not modified
- No data loss occurs

Usage:
    python scripts/migrate_add_check_call_fields.py

Note:
    Run this script before deploying the new code to production.
    The application will work correctly even if migration hasn't run yet
    (new fields will be None/False by default).
"""

import sqlite3
from pathlib import Path


def get_db_path() -> str:
    """Get database path from environment or use default."""
    import os

    db_url = os.getenv("DATABASE_URL", "sqlite:///./loyalty.db")
    # Extract path from SQLite URL
    if db_url.startswith("sqlite:///"):
        return db_url.replace("sqlite:///", "")
    return "./loyalty.db"


def column_exists(cursor, table_name, column_name) -> bool:
    """Check if a column exists in a table."""
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [row[1] for row in cursor.fetchall()]
    return column_name in columns


def migrate():
    """Run database migration."""
    db_path = get_db_path()

    print(f"[MIGRATION] Using database: {db_path}")

    # Check if database file exists
    if not Path(db_path).exists():
        print("[MIGRATION] Database file not found. Will be created on first run.")
        return

    # Connect to database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Add sms_check_id column
        if not column_exists(cursor, "users", "sms_check_id"):
            print("[MIGRATION] Adding column: sms_check_id")
            cursor.execute("ALTER TABLE users ADD COLUMN sms_check_id VARCHAR(50)")
            print("  ✓ Column sms_check_id added")
        else:
            print("[MIGRATION] Column sms_check_id already exists")

        # Add is_privacy_accepted column
        if not column_exists(cursor, "users", "is_privacy_accepted"):
            print("[MIGRATION] Adding column: is_privacy_accepted")
            cursor.execute(
                "ALTER TABLE users ADD COLUMN is_privacy_accepted BOOLEAN DEFAULT 0"
            )
            print("  ✓ Column is_privacy_accepted added")
        else:
            print("[MIGRATION] Column is_privacy_accepted already exists")

        # Add is_subscribed column
        if not column_exists(cursor, "users", "is_subscribed"):
            print("[MIGRATION] Adding column: is_subscribed")
            cursor.execute(
                "ALTER TABLE users ADD COLUMN is_subscribed BOOLEAN DEFAULT 0"
            )
            print("  ✓ Column is_subscribed added")
        else:
            print("[MIGRATION] Column is_subscribed already exists")

        # Commit changes
        conn.commit()
        print("\n[MIGRATION] ✓ Migration completed successfully!")

        # Show summary
        cursor.execute("SELECT COUNT(*) FROM users")
        user_count = cursor.fetchone()[0]
        print(f"[MIGRATION] Total users in database: {user_count}")

    except Exception as e:
        conn.rollback()
        print(f"\n[MIGRATION] ✗ Error: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    print("=" * 60)
    print("Check Call Database Migration")
    print("=" * 60)
    print()
    migrate()
    print()
    print("=" * 60)
