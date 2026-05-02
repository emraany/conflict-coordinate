# The Conflict Coordinate — project context

Neutral platform that visualizes active global conflicts on an interactive 3D globe. Every claim is traceable to a cited source.

## Stack

- **Backend:** Python 3.12 · FastAPI · SQLAlchemy · Alembic · Pydantic · managed with `uv`
- **Database:** PostgreSQL 16 + PostGIS (via Docker Compose locally)
- **Frontend:** Vite · React 18 · TypeScript · `react-globe.gl`
- **Admin auth:** single `ADMIN_TOKEN` env var, sent as `X-Admin-Token` header
- **Ingestion:** pluggable `IngestionSource` ABC. Sources: `FixtureSource` (seed data), `ACLEDSource` (real OAuth + event aggregation), `GDELTSource` (supplementary event stream, attach-only), `UCDPSource` (Uppsala GED, attach-only).

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

## Coding guidelines (Karpathy)

Bias toward caution over speed; for trivial tasks use judgment.

1. **Think before coding.** State assumptions explicitly. If multiple interpretations exist, surface them — don't pick silently. If something's unclear, stop and ask. Push back when a simpler approach exists.
2. **Simplicity first.** Minimum code that solves the problem. No speculative features, no abstractions for single-use code, no flexibility/configurability that wasn't requested, no error handling for impossible scenarios. If 200 lines could be 50, rewrite.
3. **Surgical changes.** Touch only what's required. Don't "improve" adjacent code, comments, or formatting. Don't refactor what isn't broken. Match existing style. If you spot unrelated dead code, mention it — don't delete it. Every changed line should trace directly to the request. Only remove orphans your own changes created.
4. **Goal-driven execution.** Convert tasks into verifiable goals: "fix the bug" → "write a failing test that reproduces it, then make it pass." For multi-step work, state a brief plan with a verify check per step. Loop until each check passes.


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
| `UCDP_ENABLED` | `false` | Enable UCDP GED ingestion (attach-only) |
| `UCDP_TOKEN` | `""` | UCDP API token (x-ucdp-access-token header) |
| `UCDP_LOOKBACK_DAYS` | `730` | How far back to query events (2 years default) |
| `UCDP_GED_VERSION` | `25.1` | UCDP GED dataset version string |
| `UCDP_ATTACH_RADIUS_KM` | `150` | Max distance to attach a UCDP event to a crisis |
| `STATUS_STALE_DAYS` | `90` | Active crises with no event in this many days are demoted to `frozen` (0 disables) |
| `INGEST_SCHEDULE_HOURS` | `24` | Hours between automatic ingest runs (0 = disabled) |

ACLED OAuth tokens cached at `backend/.cache/acled_token.json` (gitignored).

## Deliberately out of scope (don't add without asking)

- LLM-API-based features (all ML must run locally with shippable weights). Abstractive summarization or narrative generation of incidents (analytical ML — NER, forecasting, precedent retrieval, extractive excerpts — is in scope).
- Multi-user admin, audit logs, edit history
- Public-facing authentication (API key access is in scope; user accounts are not)
- 2D map fallback, mobile polish

## Current status pointers

- Active plan (tasks 1–17): `/Users/emraan/.claude/plans/modular-floating-perlis.md`
- ML phase detail: `/Users/emraan/.claude/plans/inherited-watching-lighthouse.md`
- Deployment plan: `/Users/emraan/.claude/plans/fluffy-singing-clover.md`
- Memory index: `/Users/emraan/.claude/projects/-Users-emraan-Desktop-Conflict/memory/MEMORY.md`
