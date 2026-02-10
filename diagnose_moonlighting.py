#!/usr/bin/env python3
"""
Moonlighting Data Diagnostic Script
Run this on Fly.io to diagnose the Kat Egressy issue

Usage on Fly.io:
    fly ssh console
    cd /app
    python diagnose_moonlighting.py
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path

# Find the database
DB_PATHS = [
    "/data/facultyhub.db",
    "/app/data/facultyhub.db", 
    "./facultyhub.db",
    "../data/facultyhub.db"
]

def find_database():
    """Find the database file"""
    for path in DB_PATHS:
        if Path(path).exists():
            print(f"✅ Found database: {path}")
            return path
    print("❌ Database not found in expected locations:")
    for path in DB_PATHS:
        print(f"   - {path}")
    return None

def test_date_parsing(date_str):
    """Test if date string parses correctly"""
    if not date_str or not date_str.strip():
        return None, "Empty"
    
    parts = [p.strip() for p in str(date_str).split(',') if p.strip()]
    parsed = []
    failed = []
    
    for p in parts:
        try:
            # Try YYYY-MM-DD
            d = datetime.strptime(p, "%Y-%m-%d").date()
            parsed.append(d.isoformat())
        except Exception:
            try:
                # Try MM/DD/YYYY
                d = datetime.strptime(p, "%m/%d/%Y").date()
                parsed.append(d.isoformat())
            except Exception:
                failed.append(p)
    
    return parsed, failed

def diagnose():
    """Run full diagnostic"""
    print("=" * 80)
    print("MOONLIGHTING DIAGNOSTIC TOOL")
    print("=" * 80)
    print()
    
    # Find database
    db_path = find_database()
    if not db_path:
        return
    
    # Connect to database
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        print("✅ Connected to database")
        print()
    except Exception as e:
        print(f"❌ Failed to connect: {e}")
        return
    
    # Check if moonlighting tables exist
    print("📋 Checking database schema...")
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [row[0] for row in cursor.fetchall()]
    print(f"   Tables found: {', '.join(tables)}")
    print()
    
    moonlighting_tables = [t for t in tables if 'moonlight' in t.lower()]
    if not moonlighting_tables:
        print("❌ No moonlighting tables found!")
        print("   Available tables:", ', '.join(tables))
        return
    
    print(f"✅ Moonlighting tables: {', '.join(moonlighting_tables)}")
    print()
    
    # Get moonlighting requests
    print("=" * 80)
    print("MOONLIGHTING REQUESTS DATA")
    print("=" * 80)
    print()
    
    for table in moonlighting_tables:
        if 'request' in table.lower():
            print(f"📊 Examining table: {table}")
            print()
            
            # Get all requests
            cursor.execute(f"SELECT * FROM {table}")
            rows = cursor.fetchall()
            
            if not rows:
                print("   No data found")
                continue
            
            # Show column names
            columns = [desc[0] for desc in cursor.description]
            print(f"   Columns: {', '.join(columns)}")
            print()
            
            # Analyze each request
            for row in rows:
                row_dict = dict(row)
                faculty_id = row_dict.get('faculty_id', 'N/A')
                name = row_dict.get('name', 'N/A')
                desired = row_dict.get('desired_nights', 'N/A')
                requested_dates = row_dict.get('requested_dates', '')
                
                print(f"   👤 {name} ({faculty_id})")
                print(f"      Desired: {desired} nights")
                print(f"      Requested dates (raw): {repr(requested_dates)}")
                
                # Test date parsing
                if requested_dates:
                    parsed, failed = test_date_parsing(requested_dates)
                    if parsed:
                        print(f"      ✅ Parsed: {', '.join(parsed)}")
                    if failed:
                        print(f"      ❌ FAILED TO PARSE: {', '.join(failed)}")
                else:
                    print(f"      ⚠️  No dates requested")
                print()
    
    # Get schedule assignments
    print("=" * 80)
    print("SCHEDULE ASSIGNMENTS")
    print("=" * 80)
    print()
    
    for table in moonlighting_tables:
        if 'assignment' in table.lower() or 'schedule' in table.lower():
            print(f"📊 Examining table: {table}")
            print()
            
            cursor.execute(f"SELECT * FROM {table}")
            rows = cursor.fetchall()
            
            if not rows:
                print("   No assignments found")
                continue
            
            # Group by faculty
            from collections import defaultdict
            by_faculty = defaultdict(list)
            
            for row in rows:
                row_dict = dict(row)
                fid = row_dict.get('faculty_id') or row_dict.get('provider_id')
                date = row_dict.get('date') or row_dict.get('shift_date')
                if fid and date:
                    by_faculty[fid].append(date)
            
            for fid, dates in sorted(by_faculty.items()):
                print(f"   {fid}: {', '.join(sorted(dates))}")
    
    # KAT EGRESSY SPECIFIC ANALYSIS
    print()
    print("=" * 80)
    print("🔍 KAT EGRESSY SPECIFIC ANALYSIS")
    print("=" * 80)
    print()
    
    for table in moonlighting_tables:
        if 'request' in table.lower():
            cursor.execute(f"""
                SELECT * FROM {table} 
                WHERE name LIKE '%Kat%' OR name LIKE '%Egressy%'
                OR faculty_id LIKE '%Kat%' OR faculty_id LIKE '%Egressy%'
            """)
            rows = cursor.fetchall()
            
            for row in rows:
                row_dict = dict(row)
                print("📋 REQUEST DATA:")
                for key, value in row_dict.items():
                    print(f"   {key}: {repr(value)}")
                print()
                
                # Parse dates
                requested_dates = row_dict.get('requested_dates', '')
                if requested_dates:
                    print("🔬 DATE PARSING TEST:")
                    parsed, failed = test_date_parsing(requested_dates)
                    print(f"   Raw input: {repr(requested_dates)}")
                    print(f"   Successfully parsed: {parsed}")
                    print(f"   Failed to parse: {failed}")
                    print()
    
    for table in moonlighting_tables:
        if 'assignment' in table.lower() or 'schedule' in table.lower():
            cursor.execute(f"""
                SELECT * FROM {table}
                WHERE faculty_id LIKE '%Kat%' OR faculty_id LIKE '%Egressy%'
                OR provider_id LIKE '%Kat%' OR provider_id LIKE '%Egressy%'
                OR provider_name LIKE '%Kat%' OR provider_name LIKE '%Egressy%'
            """)
            rows = cursor.fetchall()
            
            if rows:
                print("📅 ASSIGNMENT DATA:")
                for row in rows:
                    row_dict = dict(row)
                    for key, value in row_dict.items():
                        print(f"   {key}: {repr(value)}")
                    print()
    
    conn.close()
    print("=" * 80)
    print("DIAGNOSTIC COMPLETE")
    print("=" * 80)

if __name__ == "__main__":
    try:
        diagnose()
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
