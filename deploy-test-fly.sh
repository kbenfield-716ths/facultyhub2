#!/usr/bin/env bash
#
# Deploy a STANDALONE throwaway FacultyHub test instance to Fly.io for
# security/vulnerability testing — completely separate from PCCM production.
#
# What it does:
#   1. Verifies you're logged in to Fly (you must run `flyctl auth login` first)
#   2. Creates the app + a dedicated volume (distinct names, never prod's)
#   3. Sets random secrets: SECRET_KEY + admin/test-user passwords
#   4. Deploys, then prints the URL and the two logins
#
# The passwords are generated locally and shown ONLY in your terminal — they
# are never written to the repo. This is a disposable instance: destroy it
# with `fly apps destroy $APP_NAME` when you're done testing.
#
# Override the app name if the default is taken:  APP_NAME=my-name ./deploy-test-fly.sh
set -euo pipefail

APP_NAME="${APP_NAME:-dom-facultyhub-test}"
REGION="${REGION:-iad}"
VOLUME="dom_test_data"
CONFIG="fly.test.toml"

# --- Guardrail: never operate on a production-looking app name -------------
case "$APP_NAME" in
  *moonlighter*|facultyhub|*pccm*)
    echo "REFUSING: '$APP_NAME' looks like a production app. Choose a test name." >&2
    exit 1 ;;
esac

command -v flyctl >/dev/null 2>&1 || { echo "flyctl not found. Install: https://fly.io/docs/flyctl/install/" >&2; exit 1; }

echo "==> Checking Fly auth..."
if ! flyctl auth whoami >/dev/null 2>&1; then
  echo "You are not logged in to Fly. Run:  flyctl auth login" >&2
  exit 1
fi
echo "    Logged in as: $(flyctl auth whoami 2>/dev/null)"

# --- Create app (idempotent) ----------------------------------------------
if flyctl apps list 2>/dev/null | awk '{print $1}' | grep -qx "$APP_NAME"; then
  echo "==> App '$APP_NAME' already exists — reusing."
else
  echo "==> Creating app '$APP_NAME'..."
  flyctl apps create "$APP_NAME"
fi

# --- Secrets: SECRET_KEY + seed passwords ---------------------------------
gen() { LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c "${1:-32}"; }
SECRET_KEY="$(gen 48)"
ADMIN_PW="$(gen 20)"
TEST_PW="$(gen 20)"

echo "==> Setting secrets (staged; applied on deploy)..."
flyctl secrets set --app "$APP_NAME" --stage \
  SECRET_KEY="$SECRET_KEY" \
  ADMIN_SEED_PASSWORD="$ADMIN_PW" \
  TEST_SEED_PASSWORD="$TEST_PW" >/dev/null

# --- Volume (idempotent) ---------------------------------------------------
if flyctl volumes list --app "$APP_NAME" 2>/dev/null | grep -q "$VOLUME"; then
  echo "==> Volume '$VOLUME' already exists — reusing."
else
  echo "==> Creating volume '$VOLUME' (1GB, $REGION)..."
  flyctl volumes create "$VOLUME" --app "$APP_NAME" --region "$REGION" --size 1 --yes
fi

# --- Deploy ----------------------------------------------------------------
echo "==> Deploying..."
flyctl deploy --app "$APP_NAME" --config "$CONFIG" --region "$REGION"

URL="https://${APP_NAME}.fly.dev"
cat <<EOF

============================================================
  Test instance deployed.

  URL:    $URL
  Admin:  ADMIN   /  $ADMIN_PW
  Tester: TESTER  /  $TEST_PW   (non-admin, division: MICU APPs)

  These passwords were generated just now and are shown only
  here. Re-running this script rotates them.

  This is a DISPOSABLE instance. When done:
    flyctl apps destroy $APP_NAME
============================================================
EOF
