# Google Photo Downloader

> Self-hosted, Docker-deployable Google Photos sync — download your entire library in original quality, organized by date and album, with a built-in web browser and continuous monitoring.

---

## Features

| Feature | Details |
|---|---|
| **Original quality** | Downloads photos & videos at their highest Google-stored resolution |
| **Date organization** | `{dest}/2024/01 - January/photo.jpg` |
| **Album folders** | `{dest}/Albums/My Album/` (symlinks, no duplicate storage) |
| **Location data** | GPS coordinates preserved in EXIF + stored in the database |
| **Continuous monitoring** | Auto-syncs every N minutes, picks up new uploads |
| **Resume & throttle** | Survives network drops; configurable MB/s speed cap |
| **Error correction** | Failed downloads are retried; validation after each file |
| **Web UI** | Dashboard, photo browser (source vs. local), sync log, settings |
| **Authentication** | Username/password with configurable session timeout |
| **Docker-ready** | Single `docker compose up` deployment |

---

## Quick Start

```bash
# 1. Clone
git clone https://github.com/YOUR_USERNAME/google-photo-downloader.git
cd google-photo-downloader

# 2. Create your private config (never committed to git)
cp .env.example env/.env
nano env/.env          # Fill in your values – see SETUP.md

# 3. Build & run
docker compose up -d

# 4. Open the web UI
open http://localhost:8080
```

Log in with the `WEB_USERNAME` / `WEB_PASSWORD` from your `.env` file, then go to **Settings → Connect Google Account**.

---

## Project Structure

```
google-photo-downloader/
├── app/                    # FastAPI application
│   ├── main.py             # Entry point
│   ├── config.py           # Settings (pydantic-settings)
│   ├── auth/               # JWT web auth
│   ├── google/             # Google Photos OAuth + API client
│   ├── sync/               # Download engine (throttle, resume, validate)
│   ├── storage/            # File organizer + thumbnail generator
│   ├── api/                # REST API routers
│   ├── database/           # SQLAlchemy models + SQLite
│   └── static/             # Frontend (HTML/CSS/JS — no build step)
├── deploy/
│   ├── lxc/deploy.sh       # One-command Proxmox LXC deployment
│   └── systemd/            # Optional systemd service wrapper
├── env/                    # ← GITIGNORED — your private credentials
│   ├── .env
│   └── credentials/        # google_token.json goes here (auto-created)
├── .env.example            # Template — safe to commit
├── Dockerfile
└── docker-compose.yml
```

---

## Destination Folder Layout

```
/your/photos/
├── 2024/
│   ├── 01 - January/
│   │   ├── IMG_1234.jpg
│   │   └── VID_5678.mp4
│   └── 02 - February/
├── 2025/
│   └── ...
├── Albums/
│   ├── Vacation 2024/
│   │   └── IMG_1234.jpg -> ../../2024/01 - January/IMG_1234.jpg
│   └── Family/
└── Unknown/                # Items with no date metadata
```

---

## Configuration Reference

All settings live in `env/.env` (see `.env.example` for full list).

| Variable | Default | Description |
|---|---|---|
| `WEB_USERNAME` | `admin` | Web UI login username |
| `WEB_PASSWORD` | `changeme` | Web UI login password |
| `SECRET_KEY` | *(random)* | JWT signing secret — generate with `openssl rand -hex 32` |
| `SESSION_TIMEOUT_MINUTES` | `60` | Options: 15, 60, 1440, 10080 |
| `GOOGLE_CLIENT_ID` | — | From Google Cloud Console |
| `GOOGLE_CLIENT_SECRET` | — | From Google Cloud Console |
| `GOOGLE_REDIRECT_URI` | `http://localhost:8080/api/google/callback` | Must match Google Console config |
| `DESTINATION_PATH` | `/data/photos` | Where photos are saved (inside container) |
| `SPEED_LIMIT_MBPS` | `0` | Download speed cap (0 = unlimited) |
| `SYNC_INTERVAL_MINUTES` | `60` | How often to check for new photos |
| `MAX_RETRIES` | `3` | Retry attempts for failed downloads |

---

## Updating

```bash
git pull
docker compose pull   # if using a registry image
docker compose up -d --build
```

---

## Security Notes

- Web UI is protected by username/password with `httponly` cookie sessions.
- Google Photos access is read-only (`photoslibrary.readonly` scope).
- The `env/` folder is gitignored — your credentials stay local.
- Run behind a reverse proxy (Nginx/Caddy) with HTTPS for public exposure.

---

## License

MIT
