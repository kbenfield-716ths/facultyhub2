# Database Migrations

This directory contains safe, tested migration scripts for implementing the code review recommendations.

## Available Migrations

### 1. migrate_sessions_to_db.py
**Purpose:** Move sessions from in-memory dictionary to database-backed SessionToken model

**Impact:** All users will need to log in again after deployment

**Risk Level:** LOW - No data loss, easily reversible

**Usage:**
```bash
cd /path/to/FacultyHub
python3 migrations/migrate_sessions_to_db.py
```

**What it does:**
- Backs up current auth.py
- Generates new auth.py that uses SessionToken model
- Provides instructions for updating routes/auth.py
- Creates rollback instructions

**Testing:**
```bash
# Start test server
cd backend && uvicorn app:app --port 8001

# Test login at http://localhost:8001/login.html
# Restart server and verify session persists
```

### 2. consolidate_faculty_provider.py
**Purpose:** Eliminate Provider table, use Faculty for all moonlighting

**Impact:** Removes dual table structure, simplifies codebase

**Risk Level:** MEDIUM - Database structure change, but all data preserved

**Usage:**
```bash
cd /path/to/FacultyHub
python3 migrations/consolidate_faculty_provider.py --database moonlighter_test.db

# For production (after testing):
python3 migrations/consolidate_faculty_provider.py --database moonlighter.db --no-test
```

**What it does:**
- Creates timestamped backup
- Validates preconditions
- Updates foreign keys in signups and assignments tables
- Removes Provider table
- Validates data integrity
- Provides code update instructions

**Testing:**
```bash
# Use test database first!
python3 migrations/consolidate_faculty_provider.py --database moonlighter_test.db

# Then test moonlighting features:
# - Submit signup
# - Run optimizer
# - View assignments
```

## Migration Order

**Phase 1: Safe Code Cleanup** (No migrations needed)
- Delete duplicate code
- Consolidate get_db()
- Clean up files

**Phase 2: Terminology Updates** (No migrations needed)
- Update frontend labels
- Consolidate password endpoints

**Phase 3: Database Changes** (USE THESE MIGRATIONS)
1. First: `migrate_sessions_to_db.py`
2. Then: `consolidate_faculty_provider.py`

## Safety Features

All migrations include:
- ✅ Automatic backups before changes
- ✅ Precondition validation
- ✅ Post-migration integrity checks
- ✅ Detailed rollback instructions
- ✅ Test mode confirmation prompts

## Rollback Procedures

### For Session Migration:
```bash
# Restore auth.py
cp backend/auth.py.before_session_migration backend/auth.py

# Restart server
pkill -f uvicorn
cd backend && uvicorn app:app --port 8000
```

### For Faculty/Provider Consolidation:
```bash
# Restore database (backup path shown in migration output)
cp moonlighter_before_faculty_provider_merge_YYYYMMDD_HHMMSS.db moonlighter.db

# Restore code
git checkout backend/models.py backend/app.py

# Restart server
pkill -f uvicorn
cd backend && uvicorn app:app --port 8000
```

## Testing Checklist

Before deploying any migration to production:

- [ ] Backup production database
- [ ] Run migration on test database copy
- [ ] Test all authentication flows
- [ ] Test all moonlighting features
- [ ] Verify record counts unchanged
- [ ] Check for database integrity errors
- [ ] Test rollback procedure
- [ ] Document any issues

## Support

If you encounter issues:

1. **Don't panic** - You have backups
2. **Check the migration output** - It includes specific error messages
3. **Use rollback procedure** - Restore from backup
4. **Review precondition checks** - Migration output shows what failed

## Questions?

The migration scripts are heavily commented. Read the script code for detailed understanding of what each step does.

Each script includes:
- Inline comments explaining logic
- Safety checks at each step
- Clear error messages
- Rollback instructions
