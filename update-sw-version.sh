#!/bin/bash
# Update service worker version before deployment

# Generate timestamp-based version
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
NEW_VERSION="pccm-v${TIMESTAMP}"

echo "Updating service worker to version: ${NEW_VERSION}"

# Update the CACHE_VERSION in service-worker.js
sed -i.bak "s/const CACHE_VERSION = 'pccm-v[^']*'/const CACHE_VERSION = '${NEW_VERSION}'/" service-worker.js

echo "✅ Service worker version updated to: ${NEW_VERSION}"

# Show the change
grep "CACHE_VERSION" service-worker.js | head -1
