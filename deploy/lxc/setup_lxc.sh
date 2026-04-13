#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# GrtPhotoSync – LXC Container Setup Script
# Run this INSIDE the freshly created Ubuntu 22.04 LXC container as root.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/thegrt-hash/GrtPhotoSync/main/deploy/lxc/setup_lxc.sh | bash
#   -- OR --
#   bash setup_lxc.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

APP_DIR="/opt/GrtPhotoSync"
MOUNT_POINT="/mnt/photos"
SMB_SHARE="//RaymondNas-01/General_Share/Photos"
CREDENTIALS_FILE="/etc/smb-grtphotosync.creds"
SERVICE_NAME="google-photo-downloader"

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║       GrtPhotoSync – LXC Setup               ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# ── 1. System update ─────────────────────────────────────────────────────────
echo "==> [1/7] Updating system packages…"
apt-get update -qq && apt-get upgrade -yq

# ── 2. Install dependencies ───────────────────────────────────────────────────
echo "==> [2/7] Installing required packages…"
apt-get install -yq \
  ca-certificates curl gnupg lsb-release \
  cifs-utils smbclient \
  git apt-transport-https

# ── 3. Install Docker ─────────────────────────────────────────────────────────
echo "==> [3/7] Installing Docker…"
if ! command -v docker &>/dev/null; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg

  echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
    https://download.docker.com/linux/ubuntu \
    $(lsb_release -cs) stable" \
    > /etc/apt/sources.list.d/docker.list

  apt-get update -qq
  apt-get install -yq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  systemctl enable docker
  systemctl start docker
  echo "    Docker installed: $(docker --version)"
else
  echo "    Docker already installed: $(docker --version)"
fi

# ── 4. Mount SMB share ────────────────────────────────────────────────────────
echo "==> [4/7] Configuring SMB mount for NAS photos…"
mkdir -p "$MOUNT_POINT"

# Write credentials file (root-readable only)
if [ ! -f "$CREDENTIALS_FILE" ]; then
  read -rp "    SMB username: " SMB_USER
  read -rsp "    SMB password: " SMB_PASS
  echo ""
  cat > "$CREDENTIALS_FILE" <<EOF
username=${SMB_USER}
password=${SMB_PASS}
EOF
  chmod 600 "$CREDENTIALS_FILE"
  echo "    Credentials saved to $CREDENTIALS_FILE"
else
  echo "    Credentials file already exists at $CREDENTIALS_FILE"
fi

# Add fstab entry if not present
if ! grep -q "$SMB_SHARE" /etc/fstab; then
  echo "${SMB_SHARE}  ${MOUNT_POINT}  cifs  credentials=${CREDENTIALS_FILE},uid=1000,gid=1000,file_mode=0664,dir_mode=0775,iocharset=utf8,vers=3.0,nofail,_netdev  0  0" >> /etc/fstab
  echo "    Added fstab entry"
fi

# Mount now
if ! mountpoint -q "$MOUNT_POINT"; then
  mount "$MOUNT_POINT" && echo "    Mounted $SMB_SHARE → $MOUNT_POINT" \
    || echo "    WARNING: Mount failed – check NAS is reachable and credentials are correct"
else
  echo "    Already mounted: $MOUNT_POINT"
fi

# ── 5. Clone / update the app ─────────────────────────────────────────────────
echo "==> [5/7] Cloning GrtPhotoSync from GitHub…"
if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" pull
  echo "    Repository updated"
else
  git clone https://github.com/thegrt-hash/GrtPhotoSync.git "$APP_DIR"
  echo "    Repository cloned to $APP_DIR"
fi

# ── 6. Configure environment ──────────────────────────────────────────────────
echo "==> [6/7] Setting up configuration…"
mkdir -p "$APP_DIR/env/credentials"

if [ ! -f "$APP_DIR/env/.env" ]; then
  cp "$APP_DIR/.env.example" "$APP_DIR/env/.env"
  # Patch DESTINATION_PATH and GOOGLE_REDIRECT_URI in one pass
  sed -i \
    -e "s|DESTINATION_PATH=.*|DESTINATION_PATH=/mnt/photos|" \
    -e "s|GOOGLE_REDIRECT_URI=.*|GOOGLE_REDIRECT_URI=https://GooglePhoto.sudonet.site/api/google/callback|" \
    -e "s|DATABASE_PATH=.*|DATABASE_PATH=/data/gpd.db|" \
    -e "s|LOG_PATH=.*|LOG_PATH=/data/logs|" \
    "$APP_DIR/env/.env"

  echo ""
  echo "  ┌─────────────────────────────────────────────────────────────────┐"
  echo "  │  IMPORTANT – edit $APP_DIR/env/.env and set:                   │"
  echo "  │    SECRET_KEY   → run: openssl rand -hex 32                     │"
  echo "  │    WEB_USERNAME / WEB_PASSWORD                                  │"
  echo "  │    GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET                      │"
  echo "  └─────────────────────────────────────────────────────────────────┘"
else
  echo "    .env already exists – skipping"
fi

# Update docker-compose to use the NAS mount point
sed -i "s|DESTINATION_PATH:-/mnt/photos|DESTINATION_PATH:-${MOUNT_POINT}|" \
  "$APP_DIR/docker-compose.yml" 2>/dev/null || true

# ── 7. Install systemd service + start ───────────────────────────────────────
echo "==> [7/7] Installing systemd service…"
cat > /etc/systemd/system/${SERVICE_NAME}.service <<EOF
[Unit]
Description=GrtPhotoSync – Google Photos Downloader
After=docker.service network-online.target remote-fs.target
Requires=docker.service

[Service]
Type=simple
WorkingDirectory=${APP_DIR}
ExecStart=/usr/bin/docker compose up
ExecStop=/usr/bin/docker compose down
Restart=always
RestartSec=15

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"

echo ""
echo "╔══════════════════════════════════════════════════════════════════════╗"
echo "║  Setup complete!                                                     ║"
echo "║                                                                      ║"
echo "║  Next steps:                                                         ║"
echo "║  1. Edit env:  nano ${APP_DIR}/env/.env                         ║"
echo "║  2. Start:     cd ${APP_DIR} && docker compose up -d           ║"
echo "║  3. Check:     docker compose logs -f                               ║"
echo "║  4. Web UI:    http://192.168.38.58:8080  (local test)              ║"
echo "║                https://GooglePhoto.sudonet.site  (via NPM)          ║"
echo "╚══════════════════════════════════════════════════════════════════════╝"
