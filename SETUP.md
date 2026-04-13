# Setup Guide

Step-by-step instructions for first-time deployment.

---

## Step 1 — Google Cloud Console

You need OAuth2 credentials so the app can access your Google Photos.

1. Go to **https://console.cloud.google.com/**
2. Create a new project (e.g., `photo-downloader`)
3. In the sidebar → **APIs & Services → Library**
4. Search for **"Photos Library API"** → Enable it
5. Go to **APIs & Services → OAuth consent screen**
   - User type: **External** (unless your account is a Google Workspace org)
   - Fill in App name, support email
   - Add scope: `https://www.googleapis.com/auth/photoslibrary.readonly`
   - Add your Google account email as a **Test user**
6. Go to **APIs & Services → Credentials → Create Credentials → OAuth 2.0 Client ID**
   - Application type: **Web application**
   - Add Authorized redirect URI:
     ```
     http://YOUR_HOST_IP:8080/api/google/callback
     ```
     Replace `YOUR_HOST_IP` with the IP/hostname where the app will run.
7. Download the client JSON or copy the **Client ID** and **Client Secret**

---

## Step 2 — Configure env/.env

```bash
cp .env.example env/.env
nano env/.env   # or your preferred editor
```

Required fields:
```ini
SECRET_KEY=<run: openssl rand -hex 32>
WEB_USERNAME=admin
WEB_PASSWORD=<your chosen password>

GOOGLE_CLIENT_ID=<from Google Console>
GOOGLE_CLIENT_SECRET=<from Google Console>
GOOGLE_REDIRECT_URI=http://YOUR_HOST_IP:8080/api/google/callback

DESTINATION_PATH=/data/photos   # inside container; mapped to host via docker-compose.yml
```

---

## Step 3 — Configure docker-compose.yml (host volume)

Edit `docker-compose.yml` to map `DESTINATION_PATH` to a host folder:

```yaml
volumes:
  - /mnt/nas/google-photos:/data/photos   # ← change left side to your host path
  - gpd_data:/data
```

---

## Step 4 — Start the Application

```bash
docker compose up -d
docker compose logs -f   # watch startup
```

Open **http://YOUR_HOST_IP:8080** in your browser.

---

## Step 5 — Connect Google Account

1. Log in with your `WEB_USERNAME` / `WEB_PASSWORD`
2. Go to **Settings → Connect Google Account**
3. You'll be redirected to Google — click **Allow**
4. You'll be sent back to the dashboard with a success message

The OAuth token is saved to `env/credentials/google_token.json`.

---

## Step 6 — Start Your First Sync

From the **Dashboard**, click **Start Sync**.

- The first full sync may take hours depending on library size.
- You can pause/resume at any time — downloads resume from where they left off.
- Progress is visible in real-time on the dashboard.

---

## Proxmox LXC Deployment

### One-command deploy to an existing LXC container:

```bash
./deploy/lxc/deploy.sh 192.168.1.50 root
```

This will:
1. `rsync` the application files to `/opt/google-photo-downloader` on the container
2. Install Docker if missing
3. Create the `env/.env` template if it doesn't exist

Then SSH in to complete configuration:
```bash
ssh root@192.168.1.50
nano /opt/google-photo-downloader/env/.env
cd /opt/google-photo-downloader
docker compose up -d
```

### Optional: Run as a systemd service (auto-start on boot)

```bash
# On the LXC container:
cp /opt/google-photo-downloader/deploy/systemd/google-photo-downloader.service \
   /etc/systemd/system/

systemctl daemon-reload
systemctl enable google-photo-downloader
systemctl start google-photo-downloader
```

---

## Recommended: Reverse Proxy with HTTPS

If you expose the app publicly, put it behind Nginx or Caddy:

**Caddyfile example:**
```
photos.yourdomain.com {
    reverse_proxy localhost:8080
}
```

After adding HTTPS, update `GOOGLE_REDIRECT_URI` in `env/.env`:
```ini
GOOGLE_REDIRECT_URI=https://photos.yourdomain.com/api/google/callback
```
And update the authorized redirect URI in Google Cloud Console to match.

---

## Publishing to GitHub (keeping credentials private)

The `env/` folder is listed in `.gitignore`. Your credentials will never be pushed.

```bash
git init
git remote add origin https://github.com/YOUR_USERNAME/google-photo-downloader.git
git add .
git commit -m "Initial release"
git push -u origin main
```

To give it to others, they clone the repo then follow this SETUP.md.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| "Google account not connected" on sync | Go to Settings and complete the OAuth flow |
| Photos downloading very slowly | Check `SPEED_LIMIT_MBPS` in settings or `.env` |
| `400: redirect_uri_mismatch` from Google | `GOOGLE_REDIRECT_URI` must match exactly what's in Google Console |
| Container keeps restarting | Run `docker compose logs` to check for config errors |
| Token expired / auth errors | Go to Settings → Disconnect → Reconnect Google |
| Disk full warning | Increase storage or change `DESTINATION_PATH` volume mapping |
