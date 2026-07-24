#!/usr/bin/env python3
"""
Initialize wave draft tables in the database.
Run this once to create the missing wave-based draft system tables.
"""

from backend.models import Base, engine, init_db
import sqlite3

print("=" * 60)
print("WAVE DRAFT TABLE INITIALIZATION")
print("=" * 60)

print("\n[1/3] Creating all database tables...")
try:
    Base.metadata.create_all(bind=engine)
    print("✅ Tables created successfully")
except Exception as e:
    print(f"❌ Error creating tables: {e}")
    exit(1)

print("\n[2/3] Running database initialization and optimization...")
try:
    init_db()
    print("✅ Database initialized")
except Exception as e:
    print(f"⚠️ Warning: {e}")
    print("Continuing anyway...")

print("\n[3/3] Verifying wave draft tables...")
try:
    from backend.models import db_path
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check for wave draft tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%draft%' OR name LIKE '%wave%'")
    tables = cursor.fetchall()

    if tables:
        print("✅ Wave draft tables found:")
        for table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table[0]}")
            count = cursor.fetchone()[0]
            print(f"   • {table[0]:30} ({count} rows)")
    else:
        print("❌ No wave draft tables found!")
        conn.close()
        exit(1)

    conn.close()

except Exception as e:
    print(f"❌ Verification failed: {e}")
    exit(1)

print("\n" + "=" * 60)
print("✅ INITIALIZATION COMPLETE")
print("=" * 60)
print("\nYou can now use the wave draft system in the admin panel.")
print("Deploy to Fly.io to make changes live: fly deploy")
