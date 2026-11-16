#!/usr/bin/env bash
# Pull a consistent copy of the live Faculty Hub data to THIS computer (meant for the UVA Mac mini). Run it nightly.
# The pull direction matters: nothing on Fly holds a key to this computer, so a problem on Fly cannot reach the backups.
#   One-time setup on the Mac mini:  install the Fly CLI, run `fly auth login`, turn on FileVault, then schedule this script
#   (launchd or cron), for example: 15 2 * * *  /path/to/hub/tools/backup-pull.sh >> ~/FacultyHubBackups/backup.log 2>&1
# Environment: HUB_APP (default facultyhub), HUB_BACKUP_DIR (default ~/FacultyHubBackups), HUB_BACKUP_KEEP (days, default 30),
#              HUB_BACKUP_MIN_PEOPLE (default 1; set to about your headcount so a nearly empty database is rejected).
set -euo pipefail
APP="${HUB_APP:-facultyhub}"; DEST="${HUB_BACKUP_DIR:-$HOME/FacultyHubBackups}"; KEEP="${HUB_BACKUP_KEEP:-30}"
MIN="${HUB_BACKUP_MIN_PEOPLE:-1}"; HERE="$(cd "$(dirname "$0")" && pwd)"; stamp="$(date +%Y%m%d-%H%M)"
umask 077; mkdir -p "$DEST"; chmod 700 "$DEST"
echo "[$stamp] backing up $APP"
# SQLite's own backup call gives a consistent copy even while the app is writing.
fly ssh console -a "$APP" -C "python -c \"import sqlite3;s=sqlite3.connect('/data/staff.db');d=sqlite3.connect('/data/backup.db');s.backup(d);d.close()\""
fly ssh console -a "$APP" -C "tar czf /data/uploads-backup.tgz -C /data uploads far_archive" || true   # photos and archived review files; a missing folder is not fatal
fly ssh sftp get /data/backup.db "$DEST/staff-$stamp.db.partial" -a "$APP"
fly ssh sftp get /data/uploads-backup.tgz "$DEST/files-$stamp.tgz" -a "$APP" || echo "files archive not fetched"
fly ssh console -a "$APP" -C "rm -f /data/backup.db /data/uploads-backup.tgz"
# Keep the copy only if it passes the check, so a bad pull never replaces a good one in the rotation.
PREV="$(ls -1 "$DEST"/staff-*.db 2>/dev/null | tail -1 || true)"      # the newest copy kept so far: the audit history in it must be unchanged in the new one
if python3 "$HERE/backup-verify.py" "$DEST/staff-$stamp.db.partial" "$MIN" ${PREV:+--prev "$PREV"}; then
  mv "$DEST/staff-$stamp.db.partial" "$DEST/staff-$stamp.db"
else
  mv "$DEST/staff-$stamp.db.partial" "$DEST/REJECTED-staff-$stamp.db"; echo "backup rejected; kept as REJECTED-staff-$stamp.db" >&2; exit 5
fi
# Retention: delete copies older than KEEP days.
find "$DEST" -name 'staff-*.db' -mtime +"$KEEP" -delete; find "$DEST" -name 'files-*.tgz' -mtime +"$KEEP" -delete
echo "[$stamp] done: $DEST/staff-$stamp.db"
