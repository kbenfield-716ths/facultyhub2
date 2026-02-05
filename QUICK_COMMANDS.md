# Quick Command Reference

Copy-paste commands for common operations during the migration.

## Pre-Flight Checks

```bash
# Verify Fly.io setup
fly auth whoami
fly apps list
fly status --app facultyhub

# Check database size
fly ssh console -C "ls -lh /data/moonlighter.db"
```

## Backup Production Database

```bash
# Create timestamped backup on Fly.io
fly ssh console --app facultyhub -C "cp /data/moonlighter.db /data/moonlighter.db.backup.\$(date +%Y%m%d_%H%M%S)"

# Download to local computer
fly ssh sftp get /data/moonlighter.db ./moonlighter.prod.backup.$(date +%Y%m%d).db --app facultyhub

# Verify backup downloaded
ls -lh moonlighter.prod.backup.*.db
```

## Create Staging Environment (One-Time Setup)

```bash
# Create staging app
fly apps create facultyhub-staging --org YOUR_ORG

# Create staging volume (1GB is plenty)
fly volumes create moonlighter_data_staging --region iad --app facultyhub-staging --size 1

# Copy fly.toml for staging
cp fly.toml fly.staging.toml

# Edit fly.staging.toml - change app name:
# app = 'facultyhub-staging'

# Deploy to staging
fly deploy --config fly.staging.toml
```

## Phase 1: Safe Code Cleanup

```bash
# Create branch
git checkout -b code-review-fixes

# Edit files (do these manually):
# - backend/models.py: Delete lines 1-20
# - backend/app.py: Remove get_db() function, add to imports
# - backend/routes/admin_auth.py: Remove get_db() function, add to imports
# - Remove .bak files: rm *.bak* backend/*.bak*

# Test imports work
python3 -c "from backend.models import Faculty, get_db; print('✅ Imports work')"

# Commit
git add -A
git commit -m "Phase 1: Code cleanup - remove duplicates

- Remove duplicate imports in models.py (lines 1-20)
- Consolidate get_db() to single definition in models.py
- Clean up .bak files"

# Deploy to staging (if you have it)
fly deploy --config fly.staging.toml

# Test staging
curl https://facultyhub-staging.fly.dev/health
# Visit https://facultyhub-staging.fly.dev/login.html

# Deploy to production
fly deploy --app facultyhub

# Monitor
fly logs --app facultyhub
fly status --app facultyhub
```

## Phase 2: Terminology Updates

```bash
# Make changes on same branch

# Edit login.html line 248:
# Change: <label for="facultyId">Faculty ID</label>
# To: <label for="facultyId">Faculty ID (Computing ID)</label>

# Commit
git add -A
git commit -m "Phase 2: Standardize terminology

- Clarify Faculty ID label in login form"

# Deploy
fly deploy --app facultyhub

# Test
curl https://facultyhub.fly.dev/health
# Visit login page and verify label
```

## Phase 3: Session Migration

```bash
# Backup first!
fly ssh console --app facultyhub -C "cp /data/moonlighter.db /data/moonlighter.db.before_session_migration"

# Add migration to repo
git add migrations/migrate_sessions_to_db.py
git commit -m "Phase 3: Add session migration script"

# Deploy code
fly deploy --app facultyhub

# Run migration
fly ssh console --app facultyhub
cd /app
python3 migrations/migrate_sessions_to_db.py
exit

# Restart app to use new auth.py
fly apps restart facultyhub

# Test login
# All users will need to log in again (expected)

# Monitor logs
fly logs --app facultyhub
```

## Phase 4: Faculty/Provider Consolidation

```bash
# Backup first!
fly ssh console --app facultyhub -C "cp /data/moonlighter.db /data/moonlighter.db.before_provider_merge"

# Download backup to local
fly ssh sftp get /data/moonlighter.db.before_provider_merge ./moonlighter.backup.$(date +%Y%m%d).db --app facultyhub

# Add migration to repo
git add migrations/consolidate_faculty_provider.py
git commit -m "Phase 3: Add Faculty/Provider consolidation migration"

# Deploy code
fly deploy --app facultyhub

# Run migration
fly ssh console --app facultyhub
cd /app
python3 migrations/consolidate_faculty_provider.py --database /data/moonlighter.db

# Exit and restart
exit
fly apps restart facultyhub

# Verify database integrity
fly ssh console --app facultyhub
python3 -c "
import sqlite3
conn = sqlite3.connect('/data/moonlighter.db')
cursor = conn.cursor()
print('Faculty:', cursor.execute('SELECT COUNT(*) FROM faculty').fetchone()[0])
print('Signups:', cursor.execute('SELECT COUNT(*) FROM signups').fetchone()[0])
print('Assignments:', cursor.execute('SELECT COUNT(*) FROM assignments').fetchone()[0])

# Check for orphaned records
orphans = cursor.execute('''
    SELECT COUNT(*) FROM signups s
    LEFT JOIN faculty f ON s.provider_id = f.id
    WHERE f.id IS NULL
''').fetchone()[0]
print('Orphaned signups:', orphans, '(should be 0)')
conn.close()
"
exit

# Test moonlighting features thoroughly
```

## Emergency Rollback

### Code Rollback (Quick)

```bash
# Check release history
fly releases --app facultyhub

# Rollback to previous version
fly releases rollback v12 --app facultyhub  # Use your previous version number

# Or deploy from main branch
git checkout main
fly deploy --app facultyhub
```

### Database Rollback (Phase 3 or 4)

```bash
# SSH into app
fly ssh console --app facultyhub

# Stop writes (optional - app will restart)
# List backups
ls -lh /data/*.backup.* /data/*before_*

# Restore from backup
cp /data/moonlighter.db.backup.20260205_143022 /data/moonlighter.db

# Exit
exit

# Rollback code
fly releases rollback v12 --app facultyhub

# Or from git
git checkout main
fly deploy --app facultyhub

# Restart
fly apps restart facultyhub

# Verify
fly logs --app facultyhub
curl https://facultyhub.fly.dev/health
```

## Monitoring Commands

```bash
# Live log stream
fly logs --app facultyhub

# Check app status
fly status --app facultyhub

# Health check
curl https://facultyhub.fly.dev/health

# SSH into running app
fly ssh console --app facultyhub

# Check disk usage
fly ssh console --app facultyhub -C "df -h /data"

# View database size
fly ssh console --app facultyhub -C "ls -lh /data/*.db*"

# View recent releases
fly releases --app facultyhub

# Open dashboard in browser
fly dashboard --app facultyhub
```

## Testing Checklist

After each deployment, test these:

```bash
# Health check
curl https://facultyhub.fly.dev/health

# Login page loads
curl https://facultyhub.fly.dev/login.html

# API responds
curl https://facultyhub.fly.dev/api/auth/check

# No errors in logs
fly logs --app facultyhub | grep -i error

# Database accessible
fly ssh console --app facultyhub -C "python3 -c 'import sqlite3; c=sqlite3.connect(\"/data/moonlighter.db\"); print(\"OK\"); c.close()'"
```

## Useful Debugging Commands

```bash
# Check which version is running
fly ssh console --app facultyhub -C "git log -1 --oneline"

# View environment
fly ssh console --app facultyhub -C "env | grep -E '(PATH|PYTHON|DATABASE)'"

# Check Python version
fly ssh console --app facultyhub -C "python3 --version"

# Test database connection
fly ssh console --app facultyhub -C "python3 -c 'from backend.models import engine; print(engine)'"

# Check disk space
fly ssh console --app facultyhub -C "df -h"

# View running processes
fly ssh console --app facultyhub -C "ps aux"
```

## Cost Management

```bash
# Check current usage
fly orgs billing

# Scale down when testing
fly scale count 0 --app facultyhub-staging  # Stop staging

# Scale back up
fly scale count 1 --app facultyhub-staging

# Auto-stop already configured in fly.toml
# Machines stop after 5 min idle, start on first request
```

## Notes

- **Database path:** `/data/moonlighter.db` (persistent volume)
- **App restarts:** Happen automatically during deployment
- **Zero-downtime:** Fly.io does rolling deployments automatically
- **Logs:** Kept for 7 days
- **Backups:** Manual only (use commands above)
