#!/usr/bin/env python3
"""
Initialize test users for development/testing.
Run this script to create sample faculty members.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.models import Faculty, SessionLocal
from backend.auth import hash_password

def init_test_users():
    """Create test users for development."""
    db = SessionLocal()
    
    # Default admin (created by startup, but ensure it exists)
    admin = db.query(Faculty).filter_by(id="ADMIN").first()
    if not admin:
        admin = Faculty(
            id="ADMIN",
            name="Administrator",
            email="admin@example.com",
            is_admin=True,
            password_hash=hash_password("ChangeMe123!"),
            password_changed=False,
            registered=True,
            active=True,
            extra_config="{}",
        )
        db.add(admin)
        print("✓ Created ADMIN user")
    else:
        print("- ADMIN user already exists")

    # Test faculty members — extra_config holds any group-specific attributes
    test_faculty = [
        {
            "id": "TEST1",
            "name": "Dr. Jane Smith",
            "email": "jane.smith@example.com",
            "is_admin": False,
            "extra_config": '{"base_points": 100, "role": "APP"}',
        },
        {
            "id": "TEST2",
            "name": "Dr. John Doe",
            "email": "john.doe@example.com",
            "is_admin": False,
            "extra_config": '{"base_points": 120, "role": "APP"}',
        },
        {
            "id": "TEST3",
            "name": "Dr. Sarah Johnson",
            "email": "sarah.johnson@example.com",
            "is_admin": True,
            "extra_config": '{"base_points": 150, "role": "APP"}',
        },
    ]

    for faculty_data in test_faculty:
        existing = db.query(Faculty).filter_by(id=faculty_data["id"]).first()
        if not existing:
            faculty = Faculty(
                id=faculty_data["id"],
                name=faculty_data["name"],
                email=faculty_data["email"],
                is_admin=faculty_data["is_admin"],
                password_hash=hash_password("ChangeMe123!"),
                password_changed=False,
                registered=True,
                active=True,
                extra_config=faculty_data["extra_config"],
            )
            db.add(faculty)
            print(f"✓ Created {faculty_data['id']} - {faculty_data['name']}")
        else:
            print(f"- {faculty_data['id']} already exists")
    
    db.commit()
    db.close()
    
    print("\n" + "="*50)
    print("Test users created successfully!")
    print("="*50)
    print("\nDefault credentials for all users:")
    print("  Password: PCCM2025!")
    print("\nAdmin users:")
    print("  - ADMIN (Administrator)")
    print("  - TEST3 (Dr. Sarah Johnson)")
    print("\nRegular users:")
    print("  - TEST1 (Dr. Jane Smith)")
    print("  - TEST2 (Dr. John Doe)")
    print("\nLogin at: http://localhost:8000/login.html")
    print("="*50)

if __name__ == "__main__":
    init_test_users()
