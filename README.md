# The Conflict Coordinate

Neutral platform that visualizes active global conflicts on an interactive 3D globe. Every claim is traceable to a cited source.

**Status:** active. Live ACLED, UCDP, GDELT and ReliefWeb ingestion on a weekly
schedule; ~350 admin1 regions currently render on the globe.

## Stack

Python 3.12 + FastAPI · PostgreSQL 16 + PostGIS · Vite + React 18 + TypeScript + `react-globe.gl`.

## Run locally

Prerequisites: `uv`, `node` / `npm`, `docker` (Docker Desktop on macOS), `git`.

```bash
# Clone and enter
git clone https://github.com/emraany/conflict-coordinate.git
cd conflict-coordinate

# Environment
cp .env.example .env
# edit .env and set ADMIN_TOKEN to a long random string
#   python -c 'import secrets; print(secrets.token_urlsafe(32))'

# Database (Postgres 16 + PostGIS)
docker compose up -d

# Backend
cd backend
uv sync
uv run alembic upgrade head
uv run python -m app.ingestion.runner     # seeds fixture crises
uv run uvicorn app.main:app --reload      # http://localhost:8000

# Frontend (new terminal)
cd frontend
npm install
npm run dev                                 # http://localhost:5173
```

Open `http://localhost:5173`. Clicking a marker opens the crisis dossier. The `/admin` route accepts the `ADMIN_TOKEN` you set in `.env`.

## Project documentation

See [`CLAUDE.md`](./CLAUDE.md) for conventions, neutrality rules, and design tokens.

## Data sources

- **ACLED** — weekly admin1 aggregates drive the globe's dots and all current
  counts; individual event records (embargoed ~12 months on the Research tier)
  form the incident archive. Requires ACLED credentials.
- **UCDP** — Georeferenced Event Dataset, attach-only. Requires a token.
- **GDELT** — news-event stream attached by proximity; a freshness signal, not
  verified incident records.
- **ReliefWeb** — OCHA situation reports, stored per country. Requires a
  registered appname.
- `backend/app/seed_data.json` — curated fixture data, **dev-only**, flagged as
  non-authoritative.

All feeds are off by default; fixture data works standalone. See `.env.example`.

## Deployment

See [`DEPLOY.md`](./DEPLOY.md) — Railway (API + weekly cron ingest + PostGIS)
and Vercel (frontend).

## License

Not yet licensed. Contact the author before use.
