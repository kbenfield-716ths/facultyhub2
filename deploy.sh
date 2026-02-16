#!/bin/bash
# Deploy to Fly.io with auto-updated service worker

echo "======================================"
echo "  FacultyHub Deployment Script"
echo "======================================"
echo ""

# Step 1: Update service worker version
echo "📝 Step 1: Updating service worker version..."
./update-sw-version.sh

if [ $? -ne 0 ]; then
    echo "❌ Failed to update service worker version"
    exit 1
fi

echo ""
echo "🚀 Step 2: Deploying to Fly.io..."
fly deploy

if [ $? -ne 0 ]; then
    echo "❌ Deployment failed"
    exit 1
fi

echo ""
echo "======================================"
echo "✅ Deployment complete!"
echo "======================================"
echo ""
echo "💡 Tip: Users may need to hard refresh (Ctrl+Shift+R)"
echo "   to see changes immediately, but the service worker"
echo "   will auto-update within a few minutes."
echo ""
