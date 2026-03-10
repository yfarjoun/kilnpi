#!/usr/bin/env bash
# Build the frontend locally and deploy to the Pi via scp.
# Usage: ./scripts/deploy-frontend.sh [user@host]
set -euo pipefail

PI_HOST="${1:-kilnpi}"  # default ssh host alias; override with e.g. farjoun@kilnpi.local
REMOTE_DIR="kilnpi/frontend/dist"

cd "$(dirname "$0")/../frontend"

echo "Building frontend..."
npm run build

echo "Deploying to ${PI_HOST}:~/${REMOTE_DIR} ..."
# rsync is preferred (delta transfer), fall back to scp
if command -v rsync &>/dev/null; then
    rsync -avz --delete dist/ "${PI_HOST}:~/${REMOTE_DIR}/"
else
    ssh "${PI_HOST}" "rm -rf ~/${REMOTE_DIR} && mkdir -p ~/${REMOTE_DIR}"
    scp -r dist/* "${PI_HOST}:~/${REMOTE_DIR}/"
fi

echo "Restarting kilnpi service..."
ssh "${PI_HOST}" "systemctl --user restart kilnpi.service"

echo "Done! Frontend deployed and service restarted."
