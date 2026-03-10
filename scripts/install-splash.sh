#!/usr/bin/env bash
# Install the kilnpi-splash system service.
# Run once with sudo from the repo directory:
#   sudo bash scripts/install-splash.sh

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"

# Create /opt/kilnpi symlink pointing to the repo
if [ -L /opt/kilnpi ]; then
    echo "/opt/kilnpi symlink already exists -> $(readlink /opt/kilnpi)"
elif [ -e /opt/kilnpi ]; then
    echo "ERROR: /opt/kilnpi exists and is not a symlink" >&2
    exit 1
else
    ln -s "$REPO_DIR" /opt/kilnpi
    echo "Created symlink /opt/kilnpi -> $REPO_DIR"
fi

# Install and enable system-level service
ln -sf /opt/kilnpi/kilnpi-splash.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable kilnpi-splash.service
echo "Enabled system-level kilnpi-splash.service"
echo ""
echo "If you previously had a user-level splash service, disable it once:"
echo "  systemctl --user disable --now kilnpi-splash.service"
