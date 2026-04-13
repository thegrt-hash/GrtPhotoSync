# env/ — Private Configuration (NOT committed to git)

This folder holds your personal credentials and environment settings.
It is listed in `.gitignore` and will never be pushed to GitHub.

## Structure

```
env/
├── .env                   ← Your actual configuration (copy from ../.env.example)
└── credentials/
    └── google_token.json  ← Created automatically after Google OAuth
```

## Setup

```bash
cp ../.env.example .env
# Then edit .env with your values
nano .env
```

The `credentials/` folder will be populated automatically after you complete
the Google OAuth flow inside the web UI.
