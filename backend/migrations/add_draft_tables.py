"""
Add draft system tables
"""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import engine

SQL = """
CREATE TABLE IF NOT EXISTS draft_rounds (
    id TEXT PRIMARY KEY,
    year INTEGER NOT NULL,
    round_number INTEGER DEFAULT 1,
    status TEXT DEFAULT 'pending',
    window_size INTEGER DEFAULT 5,
    hours_per_slot INTEGER DEFAULT 72,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS draft_slots (
    id TEXT PRIMARY KEY,
    round_id TEXT NOT NULL,
    faculty_id TEXT NOT NULL,
    priority_order INTEGER NOT NULL,
    status TEXT DEFAULT 'waiting',
    notified_at TIMESTAMP,
    deadline TIMESTAMP,
    submitted_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (round_id) REFERENCES draft_rounds(id) ON DELETE CASCADE,
    FOREIGN KEY (faculty_id) REFERENCES faculty(id)
);

CREATE INDEX IF NOT EXISTS idx_draft_slots_round ON draft_slots(round_id);
CREATE INDEX IF NOT EXISTS idx_draft_slots_faculty ON draft_slots(faculty_id);
CREATE INDEX IF NOT EXISTS idx_draft_slots_status ON draft_slots(status);
"""

def run_migration():
    with engine.connect() as conn:
        conn.execute(SQL)
        conn.commit()
    print("✅ Draft tables created successfully")

if __name__ == "__main__":
    run_migration()
