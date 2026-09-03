# Deployment — Railway (API + ingest + database) and Vercel (frontend)

Three Railway services and one Vercel project. The ingest worker is a Railway
cron service: Railway runs a service's start command on a schedule and expects
it to exit, which is exactly what `python -m app.ingestion.runner` does.

Cadence is **weekly** because ACLED's aggregates publish weekly — the layer the
globe is built on cannot be fresher than that.

---

## 1. Database

Deploy the **PostGIS** template (PostgreSQL + PostGIS 3.5), not plain Postgres.
PostGIS is load-bearing, not decorative: migration `0001` runs
`CREATE EXTENSION postgis`, `admin1_polygons` stores MULTIPOLYGON geometry, and
UCDP/GDELT fall back to `ST_Contains` point-in-polygon lookups to resolve an
admin1 when a name doesn't match.

Give the volume **≥ 2 GB** — the seed dump is ~750 MB before WAL and growth.

## 2. API service

- Source: this repo, root directory `backend/`, Dockerfile build.
- Railway injects `PORT`; the image's CMD already reads it.
- The CMD runs `alembic upgrade head` before uvicorn, so every deploy
  migrates itself. A failed migration exits the container rather than serving
  against a schema the code no longer matches — Railway will restart-loop and
  the build logs name the failure. The cron service overrides the CMD, so
  migrations run from this service only.

Variables:

| Variable | Value |
|---|---|
| `DATABASE_URL` | reference the Postgres service's connection URL |
| `ADMIN_TOKEN` | `python -c 'import secrets; print(secrets.token_urlsafe(32))'` |
| `PRODUCTION` | `true` |
| `CORS_ORIGINS` | the Vercel production domain, e.g. `https://<project>.vercel.app` |
| `ACLED_ENABLED` / `ACLED_USERNAME` / `ACLED_PASSWORD` | ACLED credentials |
| `UCDP_ENABLED` / `UCDP_TOKEN` | UCDP GED token |
| `GDELT_ENABLED` | `true` |
| `RELIEFWEB_APPNAME` | your registered ReliefWeb appname |

`DATABASE_URL` may be pasted in Railway's bare `postgresql://` form — the
settings validator rewrites it to `postgresql+psycopg://`, since SQLAlchemy
would otherwise resolve it to psycopg2, which isn't installed.

`PRODUCTION=true` makes the app refuse to boot while `ADMIN_TOKEN` is still the
`change-me` default. That token guards every write endpoint.

## 3. Ingest service (cron)

Same repo and Dockerfile as the API — one image, two roles.

- Start command: `python -m app.ingestion.runner`
- Cron schedule: `0 6 * * 2` (Tuesdays 06:00 UTC, after ACLED's weekly publish)
- Same variables as the API. `INGEST_SCHEDULE_TIME` stays empty: the in-process
  scheduler is the wrong tool here and would double-run.

Every attempt writes a row to `ingest_runs` whether it succeeds or dies, which
is what `/api/health` reads. A single failing source no longer aborts the run.

## 4. Frontend (Vercel)

- Root directory: `frontend/`
- Framework preset: Vite (`vercel.json` pins build/output and the SPA rewrite —
  `App.tsx` routes on `window.location.pathname`, so `/about` must serve
  `index.html` instead of 404ing).
- Environment variable: `VITE_API_URL` = the Railway API's public domain.
  This is baked in at **build** time, so changing it requires a redeploy.

## 5. Seed the database

Migrations create the schema but no data, and a from-scratch ingest is slow
(ACLED paginates up to 200k events; NER drains 5k descriptions per run). Dump
locally and restore instead:

```bash
# Schema first. Deploying the API service (step 2) already did this — run it
# by hand only to get the schema up before that service exists.
cd backend
DATABASE_URL='postgresql://…railway…' uv run alembic upgrade head

# Dump local data. Use a client matching the REMOTE major version — a PG16
# pg_dump cannot feed a PG17 server. The client needs PostGIS only in the
# server, not in itself, so use plain `postgres:17-alpine`: it is multi-arch,
# while `postgis/postgis:17-3.5` publishes no arm64 build and will not run on
# an Apple Silicon machine.
#
# The three restrictions are all load-bearing (see below):
docker run --rm -e PGPASSWORD=conflict -v "$OUT:/out" --network host postgres:17-alpine \
  pg_dump -h 127.0.0.1 -p 5432 -U conflict -d conflict \
  --data-only --no-owner --no-privileges \
  --schema=public \
  --exclude-table-data=spatial_ref_sys \
  --exclude-table-data=alembic_version \
  -Fc -f /out/seed.dump

docker run --rm -v "$OUT:/out" --network host postgres:17-alpine \
  pg_restore -d 'postgresql://…railway…' --data-only --no-owner /out/seed.dump
```

Write `$OUT` to a path under `$HOME`. Colima mounts only `/Users/<you>` into
its VM, so a `-v` target anywhere else (`/tmp`, a scratch dir) silently lands
*inside the VM* and the host sees no file — with pg_dump still exiting 0.

Why each restriction is needed — all three were confirmed by restoring into a
scratch PG17 + PostGIS 3.5 before any remote database existed:

- `--schema=public` drops the `tiger` and `topology` schemas. The PostGIS image
  enables `postgis_topology` and `postgis_tiger_geocoder`, whose config tables
  ship their own seed rows; the app touches none of them.
- `--exclude-table-data=spatial_ref_sys` — PostGIS marks that table with
  `pg_extension_config_dump`, so its ~8.5k rows *are* dumped, and a fresh
  PostGIS database already has them. Restoring collides on every row and
  overwrites 3.5's SRID definitions with 3.4's.
- `--exclude-table-data=alembic_version` — step 2 already stamped the revision
  by migrating, so the dumped row is a duplicate-key error on restore.

Sequences need no special handling: `--data-only` emits `SEQUENCE SET` entries,
so the next ingest picks up after the restored ids rather than colliding.

Restore into a scratch database first if anything in the dump looks unexpected.
Wait for a real connection, not `pg_isready` — during initdb the entrypoint runs
a temporary server that answers `pg_isready` and then drops the connection.

## 6. Verify

```bash
curl https://<api>.up.railway.app/api/health     # status, aggregate week, dots
curl https://<api>.up.railway.app/api/globe | jq length   # 293 as of 2026-09-03
```

Then trigger one ingest manually before trusting the schedule (redeploy the
cron service, or `POST /api/ingest/run` with `X-Admin-Token`), and confirm a
new `ingest_runs` row lands and `/api/health` flips to `ok`.

Point an uptime monitor at `/api/health`. On a weekly cadence a broken
pipeline is otherwise invisible for a week — and `status` there describes the
*data*, not the process, so it catches a stall that still returns HTTP 200.
A monitor polling once a minute sits far under the throttle below.

**Check the throttle keys on the real caller.** Every route is limited to 120
requests/minute per client IP, and `app/rate_limit.py` derives that IP from
the *last* `X-Forwarded-For` hop, assuming exactly one proxy in front of the
app. If Railway runs two, every visitor lands in one bucket and the site
throttles itself under normal traffic. One request confirms which it is:

```bash
curl -sD - -o /dev/null https://<api>.up.railway.app/api/health | grep -i x-ratelimit
# then again from a second network (phone hotspot). Two independent
# `x-ratelimit-remaining: 119` readings mean the buckets are per-client;
# a second reading of 118 means everyone shares one — read hops[-2] instead.
```

## Attribution

The deployed site carries ACLED, UCDP, GDELT and ReliefWeb attribution on the
About page. ACLED's Research tier is granted for academic use; keep the credit
prominent and the methodology page accurate.
