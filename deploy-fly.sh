#!/bin/bash
# Deploy itsmdemo to Fly.io
# Prerequisite: flyctl installed and authenticated (flyctl auth login)

set -e

cd /home/zyde/data/itsmdemo

echo "=== Creating app (if not exists) ==="
flyctl apps create itsmdemo 2>/dev/null || echo "App already exists"

echo "=== Creating DB volume (if not exists) ==="
flyctl volumes create itsmdemo_db --region sin --size 1 --yes 2>/dev/null || echo "Volume already exists"

echo "=== Deploying... ==="
flyctl deploy --remote-only --ha=false

echo ""
echo "=== Status ==="
flyctl status

echo ""
echo "=== Open app ==="
flyctl open
