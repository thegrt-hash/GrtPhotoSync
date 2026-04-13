#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Google Photo Downloader – LXC / Proxmox Deploy Script
# ─────────────────────────────────────────────────────────────────────────────
# Usage:
#   ./deploy/lxc/deploy.sh [HOST] [SSH_USER]
#
# Prerequisites on the target LXC container:
#   - Ubuntu 22.04+ or Debian 12+
#   - Docker + Docker Compose installed (script will install if missing)
#   - SSH access from this machine
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

HOST="${1:-localhost}"
SSH_USER="${2:-root}"
APP_DIR="/opt/google-photo-downloader"
COMPOSE_FILE="docker-compose.yml"

echo "==> Deploying Google Photo Downloader to ${SSH_USER}@${HOST}"

# ── 1. Sync code (excluding dev/credentials) ──────────────────────────────
echo "==> Syncing application files…"
rsync -avz --delete \
  --exclude='.git' \
  --exclude='env/.env' \
  --exclude='env/credentials/*.json' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='.venv' \
  --exclude='data/' \
  . "${SSH_USER}@${HOST}:${APP_DIR}/"

# ── 2. Remote setup ──────────────────────────────────────────────────────
echo "==> Running remote setup…"
ssh "${SSH_USER}@${HOST}" bash <<'REMOTE'
set -euo pipefail

APP_DIR="/opt/google-photo-downloader"
cd "$APP_DIR"

# Install Docker if not present
if ! command -v docker &>/dev/null; then
  echo "Installing Docker…"
  curl -fsSL https://get.docker.com | sh
  systemctl enable docker
  systemctl start docker
fi

# Install Docker Compose plugin if not present
if ! docker compose version &>/dev/null; then
  apt-get update -qq
  apt-get install -y docker-compose-plugin
fi

# Create the env directory if it doesn't exist
mkdir -p env/credentials

# Create .env from example if it doesn't exist
if [ ! -f env/.env ]; then
  cp .env.example env/.env
  echo ""
  echo "⚠  No env/.env found – a template has been created."
  echo "   Edit ${APP_DIR}/env/.env before starting the application!"
fi

# Ensure data directories exist (adjust paths as needed)
mkdir -p /data/photos /data/logs /data/gpd /data/thumbs

echo "==> Remote setup complete"
REMOTE

echo ""
echo "==> Deployment complete!"
echo ""
echo "Next steps:"
echo "  1. SSH into the container:  ssh ${SSH_USER}@${HOST}"
echo "  2. Edit env file:           nano ${APP_DIR}/env/.env"
echo "  3. Upload Google creds:     scp credentials.json ${SSH_USER}@${HOST}:${APP_DIR}/env/credentials/"
echo "  4. Start the app:           cd ${APP_DIR} && docker compose up -d"
echo "  5. Open browser:            http://${HOST}:8080"
