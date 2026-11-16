#!/usr/bin/env bash
# Deploy Faculty Hub to the live app with an automatic version bump.
#   tools/deploy-live.sh            bump the patch number (2.1.0 -> 2.1.1) and deploy
#   tools/deploy-live.sh --minor    bump the middle number (2.1.4 -> 2.2.0)
#   tools/deploy-live.sh --major    bump the first number (2.1.4 -> 3.0.0)
#   tools/deploy-live.sh --same     deploy without bumping (a retry of a failed deploy)
# The number is written to hub/VERSION, goes into the image, shows in the page footer and at /health, and is logged in hub/DEPLOY-LOG.txt.
set -euo pipefail
cd "$(dirname "$0")/.."
cur=$(head -n1 VERSION | awk '{print $1}')
IFS=. read -r MA MI PA <<< "$cur"
case "${1:-}" in
  --major) new="$((MA+1)).0.0" ;;
  --minor) new="${MA}.$((MI+1)).0" ;;
  --same)  new="$cur" ;;
  "")      new="${MA}.${MI}.$((PA+1))" ;;
  *) echo "Unknown option $1" >&2; exit 2 ;;
esac
APP=facultyhub
# 1. The server refuses to start without a real HUB_SECRET, so make sure one is set before replacing the running copy.
SECRETS=$(fly secrets list -a "$APP" 2>/dev/null || true)     # read once into a variable: grep -q ending a pipe early would otherwise fail the pipeline
if ! grep -qw HUB_SECRET <<<"$SECRETS"; then
  echo "HUB_SECRET is not set on $APP. Set it first:  fly secrets set -a $APP HUB_SECRET=\$(openssl rand -hex 32)" >&2
  echo "(Everyone will be signed out once, which is expected.) Deploy stopped." >&2
  exit 3
fi
if ! grep -qw HUB_DATA_KEY <<<"$SECRETS"; then
  echo "WARNING: HUB_DATA_KEY is not set on $APP, so annual review answers and license numbers stay unencrypted. See tools/RESTORE.txt." >&2
fi
# 2. Known-vulnerability reports. These warn and never block, because a report on a library is not always a reason to stop a fix.
if command -v pip-audit >/dev/null 2>&1; then
  echo "--- Python packages: pip-audit"; pip-audit -r backend/requirements.txt || echo "pip-audit reported findings above (deploy continues)."
else
  echo "pip-audit is not installed (pip install pip-audit); skipping the Python vulnerability report."
fi
if [ -f frontend/package-lock.json ] && command -v npm >/dev/null 2>&1; then
  echo "--- Front-end packages: npm audit"; (cd frontend && npm audit --omit=dev --audit-level=high) || echo "npm audit reported findings above (deploy continues)."
fi
# 3. The security checks run against a throwaway database before anything is sent.
PY="${HUB_PY:-python3}"
if "$PY" -c "import fastapi" >/dev/null 2>&1; then
  (cd backend && "$PY" tests/smoke_security.py >/dev/null) || { echo "Security tests failed. Run: cd backend && $PY tests/smoke_security.py" >&2; exit 4; }
  echo "Security tests passed."
fi
echo "Deploying version $new (was $cur)"
echo "$new" > VERSION
if fly deploy -c fly.live.toml --ha=false; then
  echo "$(date '+%Y-%m-%d %H:%M') $new" >> DEPLOY-LOG.txt
  echo "Deployed $new. Check https://facultyhub.app/health shows version $new."
else
  echo "$cur" > VERSION
  echo "Deploy failed; version put back to $cur." >&2
  exit 1
fi
