# The Conflict Coordinate — project context

Neutral platform that visualizes active global conflicts on an interactive 3D globe. Every claim is traceable to a cited source.

## Stack

- **Backend:** Python 3.12 · FastAPI · SQLAlchemy · Alembic · Pydantic · managed with `uv`
- **Database:** PostgreSQL 16 + PostGIS (via Docker Compose locally)
- **Frontend:** Vite · React 18 · TypeScript · `react-globe.gl`
- **Admin auth:** single `ADMIN_TOKEN` env var, sent as `X-Admin-Token` header
- **Ingestion:** pluggable `IngestionSource` ABC. Sources: `FixtureSource` (seed data), `ACLEDSource` (real OAuth + event aggregation), `GDELTSource` (supplementary event stream, attach-only).

## Repo layout

```
backend/          FastAPI app, SQLAlchemy models, Alembic migrations, ingestion
frontend/         Vite + React SPA with react-globe.gl
docker-compose.yml    Postgres+PostGIS only
.env.example      Copy to .env and fill in ADMIN_TOKEN
CLAUDE.md         This file
```

## Run locally

```bash
# 1. Postgres
docker compose up -d

# 2. Backend
cd backend
uv sync
uv run alembic upgrade head
uv run python -m app.ingestion.runner    # seeds fixture data
uv run uvicorn app.main:app --reload     # :8000

# 3. Frontend
cd ../frontend
npm install
npm run dev                               # :5173
```

Before running the backend, copy `.env.example` to `.env` at the repo root and set `ADMIN_TOKEN`.

## Neutrality rules (non-negotiable)

- **No LLM-generated content** in crisis summaries, actor descriptions, or source titles. Those fields are authored by admins or copied from cited sources.
- **Actor roles** are limited to `party | mediator | observer | affected`. No loaded labels (no "aggressor", "terrorist", "victim").
- **Every `crisis_actors` link** should carry a `source_id` when possible; the admin UI requires it for new links.
- `backend/app/seed_data.json` is **dev-only fixture data**, flagged as such, and must never be shipped as authoritative.

## Aesthetic

"Situation-room briefing" — modern reinterpretation of a declassified typewritten document. Design tokens live in `frontend/src/styles/tokens.ts`.

- Palette: bg `#2e3338` (gunmetal), bgRaised `#3a4048`, text `#e8dcc4`, muted `#a8a294`, rules `#525862`, active `#a64a3a` (softened red, markers only), olive `#6b7354` (primary chrome), oliveLight `#8a9070`, oliveDim `#4a523c`
- Fonts: **IBM Plex Mono** (body), **Special Elite** (document headers, sparingly), **IBM Plex Serif** (summary prose)
- Chrome: document-style header, dossier-framed detail panel, bracketed status chips (`[ ACTIVE ]`), numeric list refs (`[01]`)
- No skeuomorphic paper textures. Crisp hairlines, generous whitespace, 120–180ms fades only.
- Section labels use descriptive, non-loaded terms (`PARTIES INVOLVED`, not `COMBATANTS`).

## Git workflow

- One commit per logical milestone, pushed to `origin main` immediately after.
- Imperative-mood subject, ≤72 chars. Conventional prefixes where useful: `feat(api):`, `feat(web):`, `chore:`, `fix(...)`.
- Never force-push `main`. Never `--no-verify`.
- If a pre-commit hook fails, fix the cause and make a new commit (don't amend).

## Ingestion config

All flags default to `false`/empty — fixture data works standalone.

| Env var | Default | Purpose |
|---|---|---|
| `ACLED_ENABLED` | `false` | Enable ACLED ingestion |
| `ACLED_USERNAME` | `""` | ACLED OAuth username |
| `ACLED_PASSWORD` | `""` | ACLED OAuth password |
| `ACLED_LOOKBACK_DAYS` | `90` | How far back to fetch events |
| `ACLED_CRISIS_EVENT_THRESHOLD` | `10` | Min events to create a country-year crisis |
| `GDELT_ENABLED` | `false` | Enable GDELT supplementary stream |
| `GDELT_ATTACH_RADIUS_KM` | `300` | Max distance to attach event to crisis |
| `GDELT_LOOKBACK_MINUTES` | `180` | How many minutes of GDELT exports to fetch |

ACLED OAuth tokens cached at `backend/.cache/acled_token.json` (gitignored).

## Deliberately out of scope (don't add without asking)

- ML classification, summarization, forecasting
- Multi-user admin, audit logs, edit history
- Public-facing authentication
- 2D map fallback, mobile polish
- Automated scheduled ingestion (manual trigger only)

## Current status pointers

- Plan file: `/Users/emraan/.claude/plans/fluffy-singing-clover.md`
- Memory index: `/Users/emraan/.claude/projects/-Users-emraan-Desktop-Conflict/memory/MEMORY.md`
