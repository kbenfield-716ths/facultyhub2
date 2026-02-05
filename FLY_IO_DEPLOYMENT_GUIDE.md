# Fly.io Deployment Guide for Code Review Fixes

Your production runs on Fly.io with persistent volume storage. This guide shows you how to safely test and deploy changes without disrupting production.

## Current Setup

- **App name:** `facultyhub`
- **Region:** `iad` (US East)
- **Database:** Persistent volume `moonlighter_data` mounted at `/data`
- **Auto-scaling:** Scales to zero when idle, auto-starts on requests
- **Database path:** `/data/moonlighter.db` (persistent across deployments)

## Safe Testing Strategy for Fly.io

### Option 1: Create Staging App (Recommended)

Create a complete staging environment that mirrors production:

```bash
# 1. Create staging app
fly apps create facultyhub-staging

# 2. Copy fly.toml to staging config
cp fly.toml fly.staging.toml

# Edit fly.staging.toml:
#   Change: app = 'facultyhub-staging'

# 3. Create staging volume
fly volumes create moonlighter_data_staging --region iad --app facultyhub-staging --size 1

# 4. Deploy to staging
git checkout -b code-review-fixes
# Make your Phase 1 changes here
fly deploy --config fly.staging.toml

# 5. Get staging URL
fly apps list
# Your staging URL: https://facultyhub-staging.fly.dev

# 6. Test thoroughly on staging
# - Login, test all features
# - Run migrations if needed
# - Verify everything works
```

**Advantages:**
- ✅ Complete isolation from production
- ✅ Persistent database for thorough testing
- ✅ Same infrastructure as production
- ✅ Can run both simultaneously
- ✅ Zero risk to production users

**Cost:** ~$1-2/month for staging volume (1GB is plenty)

### Option 2: Local Testing with Docker (Free)

Test locally with the exact same environment:

```bash
# 1. Build Docker image locally
docker build -t facultyhub-test .

# 2. Copy production database for testing
fly ssh sftp get /data/moonlighter.db ./moonlighter_test.db

# 3. Run local container
docker run -p 8001:8080 \
  -v $(pwd)/moonlighter_test.db:/data/moonlighter.db \
  facultyhub-test

# 4. Test at http://localhost:8001
```

**Advantages:**
- ✅ Free
- ✅ Uses exact production Docker image
- ✅ Tests with production data
- ✅ Fast iteration

**Limitations:**
- ⚠️ Not identical to Fly.io infrastructure
- ⚠️ Need Docker installed locally

### Option 3: Blue-Green Deployment

Keep production running, deploy new version alongside:

```bash
# 1. Create blue-green app
fly apps create facultyhub-v2

# 2. Deploy new version
fly deploy --app facultyhub-v2

# 3. Test new version
# Visit https://facultyhub-v2.fly.dev

# 4. If good, swap DNS
fly certs add facultyhub-v2.fly.dev --app facultyhub-v2

# 5. Destroy old app after validation
fly apps destroy facultyhub
```

## Phase-by-Phase Deployment

### Phase 1: Code Cleanup (Zero Risk)

These changes are safe to deploy directly to production:

```bash
# 1. Make changes on branch
git checkout -b code-review-fixes

# Edit backend/models.py - delete lines 1-20
# Edit backend/app.py - remove duplicate get_db()
# Edit backend/routes/admin_auth.py - remove duplicate get_db()
# Remove .bak files

# 2. Test locally with Docker (Option 2)
docker build -t facultyhub-test .
docker run -p 8001:8080 -v $(pwd):/app facultyhub-test
# Test at http://localhost:8001

# 3. Deploy to staging first (if you have it)
fly deploy --config fly.staging.toml

# 4. Test staging thoroughly
curl https://facultyhub-staging.fly.dev/health
# Login and test features

# 5. Deploy to production
git add -A
git commit -m "Phase 1: Code cleanup"
fly deploy

# 6. Monitor
fly logs
fly status
```

**Downtime:** None (zero-downtime deployment)

**Rollback if needed:**
```bash
# Get previous release
fly releases

# Rollback
fly releases rollback v12  # Use previous version number
```

### Phase 2: Terminology & Consolidation

Same process as Phase 1. These are code-only changes, no database impact.

### Phase 3: Database Migrations (Requires Care)

**IMPORTANT:** Database changes need special handling with persistent volumes.

#### Step 1: Backup Production Database

```bash
# SSH into production VM
fly ssh console

# Inside VM - create backup
cp /data/moonlighter.db /data/moonlighter.db.backup.$(date +%Y%m%d_%H%M%S)
ls -lh /data/*.backup.*
exit

# Download backup to local
fly ssh sftp get /data/moonlighter.db.backup.YYYYMMDD_HHMMSS ./moonlighter.prod.backup.db
```

#### Step 2: Test Migration on Staging/Local

```bash
# Option A: Test on staging
fly ssh console --app facultyhub-staging
cd /app
python3 migrations/migrate_sessions_to_db.py
python3 migrations/consolidate_faculty_provider.py --database /data/moonlighter.db
exit

# Option B: Test locally
python3 migrations/consolidate_faculty_provider.py --database moonlighter_test.db
```

#### Step 3: Deploy Migration to Production

```bash
# 1. Deploy code changes
git add migrations/
git commit -m "Phase 3: Add database migration scripts"
fly deploy

# 2. SSH into production
fly ssh console

# 3. Verify backup exists
ls -lh /data/*.backup.*

# 4. Run migration
cd /app
python3 migrations/migrate_sessions_to_db.py
python3 migrations/consolidate_faculty_provider.py --database /data/moonlighter.db --no-test

# 5. Verify migration
python3 -c "
import sqlite3
conn = sqlite3.connect('/data/moonlighter.db')
print('Faculty:', conn.execute('SELECT COUNT(*) FROM faculty').fetchone()[0])
print('Signups:', conn.execute('SELECT COUNT(*) FROM signups').fetchone()[0])
conn.close()
"

# 6. Exit and restart app
exit
fly apps restart facultyhub
```

#### Step 4: Monitor Post-Migration

```bash
# Watch logs
fly logs

# Check health
fly status
curl https://facultyhub.fly.dev/health

# Test login
# Visit your app URL and verify everything works
```

## Database Backup & Restore on Fly.io

### Regular Backups

```bash
# Create backup script (add to cron or run manually)
fly ssh console -C "cp /data/moonlighter.db /data/moonlighter.db.backup.\$(date +%Y%m%d)"

# Download all backups
fly ssh sftp shell
ls /data/*.backup.*
get /data/moonlighter.db.backup.20260205 ./
exit
```

### Restore from Backup

```bash
# 1. Upload backup to Fly.io
fly ssh sftp shell
put ./moonlighter.db.backup.20260205 /data/
exit

# 2. Restore
fly ssh console
cp /data/moonlighter.db.backup.20260205 /data/moonlighter.db
exit

# 3. Restart app
fly apps restart facultyhub
```

## Rollback Procedures

### Code-Only Rollback (Phase 1 & 2)

```bash
# Simple: Roll back to previous release
fly releases
fly releases rollback v12

# Or: Deploy from previous commit
git checkout main
fly deploy
```

**Downtime:** ~30 seconds

### Database Migration Rollback (Phase 3)

```bash
# 1. SSH into VM
fly ssh console

# 2. Stop application (prevents writes during restore)
# This happens automatically when you restore

# 3. Restore database
cp /data/moonlighter.db.backup.20260205 /data/moonlighter.db

# 4. Exit
exit

# 5. Rollback code
fly releases rollback v12

# 6. Restart
fly apps restart facultyhub
```

**Downtime:** 1-2 minutes

## Monitoring & Health Checks

Your app has health checks configured. Monitor during deployment:

```bash
# Real-time logs
fly logs

# Status dashboard
fly status

# Check health endpoint
curl https://facultyhub.fly.dev/health

# SSH into running instance
fly ssh console

# View metrics
fly dashboard
```

## Cost Considerations

**Current Setup:**
- 1 shared-cpu-1x VM: ~$5/month (scales to zero when idle)
- 1GB persistent volume: ~$0.15/month
- **Total: ~$5-6/month**

**With Staging:**
- Add staging VM: ~$5/month more
- Add staging volume (1GB): ~$0.15/month
- **Total: ~$10-11/month**

**Recommendation:** Add staging for peace of mind. It's worth $5/month to test safely.

## Environment Variables

Check if you have any environment variables that need updating:

```bash
# List current secrets
fly secrets list

# Set new secrets if needed
fly secrets set DATABASE_PATH=/data/moonlighter.db
fly secrets set SECURITY_MODE=strict
```

## Quick Reference Commands

```bash
# Deploy
fly deploy

# Check status
fly status

# View logs
fly logs

# SSH in
fly ssh console

# Rollback
fly releases rollback

# Scale (if needed)
fly scale count 1  # Always keep 1 running
fly scale vm shared-cpu-1x

# Database backup
fly ssh console -C "cp /data/moonlighter.db /data/backup.db"
```

## Recommended Workflow

**For Low-Risk Changes (Phase 1 & 2):**
1. Test locally with Docker
2. Deploy directly to production
3. Monitor logs for 5 minutes
4. Rollback if issues

**For Database Changes (Phase 3):**
1. Create staging app (one-time)
2. Test migration on staging
3. Backup production database
4. Deploy migration during low-traffic window
5. Monitor closely for 30 minutes
6. Keep backup for 1 week

## Next Steps

1. **Decision:** Staging app or local-only testing?
   - Staging: `fly apps create facultyhub-staging`
   - Local: Install Docker and test there

2. **Start with Phase 1** (safe regardless of approach):
   ```bash
   git checkout -b code-review-fixes
   # Make Phase 1 changes
   fly deploy
   ```

3. **Monitor results** before proceeding to Phase 2

**Need help with any of these steps?** Let me know and I can walk you through the specific Fly.io commands or create automation scripts.
