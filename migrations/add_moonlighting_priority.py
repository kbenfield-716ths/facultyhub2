"""
Migration: Add moonlighting_priority column to faculty table.

moonlighting_priority controls how the moonlighting optimizer treats a
faculty member's date requests:
  1 = High  — requests are filled first (use for faculty who must travel)
  2 = Medium — default for all faculty
  3 = Low   — filled last, after higher-priority faculty are satisfied

Run once against the live database:
    fly ssh console -C "python migrations/add_moonlighting_priority.py"
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.models import engine
from sqlalchemy import text

def run():
    with engine.connect() as conn:
        # Check whether the column already exists (SQLite-safe)
        result = conn.execute(text("PRAGMA table_info(faculty)"))
        columns = [row[1] for row in result.fetchall()]

        if "moonlighting_priority" in columns:
            print("[migration] Column 'moonlighting_priority' already exists — skipping.")
            return

        conn.execute(text(
            "ALTER TABLE faculty ADD COLUMN moonlighting_priority INTEGER NOT NULL DEFAULT 2"
        ))
        conn.commit()
        print("[migration] Added 'moonlighting_priority' column to faculty table (default = 2).")

if __name__ == "__main__":
    run()
