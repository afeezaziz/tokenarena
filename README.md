# Token Battles

An engaging, informative, and entertaining market dashboard inspired by CoinGecko. Shows market stats, token holders and token counts with charts.

## Stack
- Flask (web)
- SQLAlchemy (ORM)
- Gunicorn (production server)
- SQLite by default (configurable via `DATABASE_URL`)

## Quickstart (uv)
Prerequisites: [uv](https://github.com/astral-sh/uv) and Python 3.11+

```bash
# Create virtual env with Python 3.11 (or 3.12)
uv venv --python 3.11

# Add dependencies
uv add flask gunicorn sqlalchemy python-dotenv

# Seed the database with sample data
uv run python seed.py

# Run locally (Flask dev server)
uv run python -c "from app import create_app; app = create_app(); app.run(debug=True)"

# Or run with gunicorn
uv run gunicorn -w 2 -b 0.0.0.0:8000 wsgi:app
```

## Configuration
Create a `.env` file (copy `.env.example`).

- `DATABASE_URL`: SQLAlchemy URL (default: `sqlite:///token_battles.db`)
- `SECRET_KEY`: Flask secret key
- `DEBUG`: `1` to enable debug

## Data Source
Currently seeded with synthetic data. The next step is to add an LNFI scraper that writes into the same database tables:

- `tokens` – latest snapshot per token (price, mcap, holders, 24h change)
- `token_snapshots` – historical per-token snapshots
- `global_metrics` – historical ecosystem rollups (total tokens, holders, market cap, 24h volume)

## Project Structure
```
.
├─ app/
│  ├─ __init__.py        # Flask app factory
│  ├─ models.py          # SQLAlchemy ORM models and session helpers
│  ├─ routes.py          # UI routes
│  ├─ api.py             # JSON APIs for stats and charts
│  └─ templates/
│     ├─ base.html
│     └─ index.html
│  └─ static/
│     ├─ css/main.css
│     └─ js/main.js
├─ seed.py               # Populate database with sample data
├─ wsgi.py               # Gunicorn entrypoint
├─ config.py             # App configuration
├─ .env.example
└─ pyproject.toml
```

## Notes
- The front page fetches `/api/overview`, `/api/tokens`, and `/api/chart/global` to render stats, a token table, and two charts (tokens over time, holders over time).
- Light-mode UI with brand accents. Token table includes 7d/30d sparklines, sortable columns, server-side pagination with page-size selector, client filter (symbol/name), and CSV export (current page).
- Global charts and token charts support range toggles: `7D/30D/90D/All`.
- Global search bar queries `/api/search?q=` for tokens and users.
- Designed to be extended to a real LNFI scraper for live data ingestion.

### API reference
- `GET /api/tokens` parameters:
  - `page` (int, default 1)
  - `page_size` (int, default 10, max 100)
  - `sort` (`symbol|price_usd|market_cap_usd|holders_count|change_24h|last_updated`)
  - `dir` (`asc|desc`)
  - `q` (filter by symbol or name, case-insensitive)
  - `sparkline` (`1|true|yes` to include per-token `sparkline` array)
  - `days` (int window for sparkline, e.g., 7 or 30)
  - Response shape: `{ items: [...], page, page_size, total }`

- `GET /api/top-movers?limit=5` — tokens with the largest absolute 24h change.
- `GET /api/chart/global?range=7d|30d|90d|all`
- `GET /api/token/<symbol>` — token details + top holders
- `GET /api/chart/token/<symbol>?range=7d|30d|90d|all`
- `GET /api/search?q=` — tokens and users

#### Auth & Profile
- `POST /api/auth/nostr/challenge` — request a short-lived nonce for the given pubkey (hex)
- `POST /api/auth/nostr/verify` — verify signed event; establishes session
- `GET /api/auth/me` — returns current session user
- `POST /api/auth/logout` — clears session
- `GET /api/profile` — returns current user's profile `{ npub, npub_bech32, display_name, avatar_url, bio, joined_at }`
- `POST /api/profile` — updates profile; accepts `{ display_name?, bio? }`
- `POST /api/profile/avatar` — multipart/form-data with `avatar` (PNG/JPEG/WebP up to 2MB by default). Stores under `app/static/uploads/avatars/` and returns `{ ok, avatar_url }`.

### Settings page
- Route: `/settings` (redirects to `/` if not logged in)
- Frontend: `app/static/js/settings.js` calls `/api/profile` GET/POST
  to load and save `display_name` and `bio`.

### Environment
- `SECRET_KEY` — set a non-default value in production
- `DEBUG` — `0` or `1`
- `DATABASE_URL` — default `sqlite:///token_battles.db`
- `SESSION_LIFETIME_SECONDS` — default `2592000` (30 days; permanent sessions)
- `LIMITER_STORAGE_URI` — rate limiter backend; default `memory://`.
  For production, use Redis, e.g. `redis://localhost:6379`.

### Nostr Sign-In

This app supports "Sign in with Nostr" via NIP-07 (browser extension) and BIP-340 Schnorr verification on the server.

Dependencies:
- `coincurve` for signature verification
- `bech32` for NIP-19 npub encoding
- `flask-limiter` for basic rate limiting

Endpoints:
- `POST /api/auth/nostr/challenge` — request a short-lived challenge
  - Body: `{ "pubkey": "<hex-64>" }`
  - Response: `{ "nonce": "...", "expires_at": "..." }`
- `POST /api/auth/nostr/verify` — verify signed event and establish session
  - Body: `{ "event": { id,pubkey,created_at,kind,tags,content,sig } }`
  - Verifies NIP-01 event id and BIP-340 signature
- `GET /api/auth/me` — returns `{ user: { npub, npub_bech32, display_name } }` when logged in
- `POST /api/auth/logout` — clears session

Front-end integration:
- Header includes a "Sign in with Nostr" button if no session; otherwise shows user label and a Logout button.
- Uses `window.nostr` (NIP-07) to sign an event containing the server-issued nonce.
- Code: `app/static/js/auth.js`. Container: `#auth-area` in `app/templates/base.html`.

Security:
- Challenge nonces live in `auth_challenges` with expiry and one-time use.
- Session cookies hardened via `SESSION_COOKIE_HTTPONLY`, `SAMESITE=Lax`, `SECURE` (when not DEBUG).
- Rate limits applied to auth endpoints.

Environment:
```
SECRET_KEY=change-me
DEBUG=0
SESSION_LIFETIME_SECONDS=2592000
```

