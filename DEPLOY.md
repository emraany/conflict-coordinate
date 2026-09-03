# Deployment — Railway (API + ingest + database) and Vercel (frontend)

Three Railway services and one Vercel project. The ingest worker is a Railway
cron service: Railway runs a service's start command on a schedule and expects
it to exit, which is exactly what `python -m app.ingestion.runner` does.

Cadence is **weekly** because ACLED's aggregates publish weekly — the layer the
globe is built on cannot be fresher than that.

---

## 1. Database

PostGIS is load-bearing, not decorative: migration `0001` runs
`CREATE EXTENSION postgis`, `admin1_polygons` stores MULTIPOLYGON geometry, and
UCDP/GDELT fall back to `ST_Contains` point-in-polygon lookups to resolve an
admin1 when a name doesn't match. Plain Postgres will not do.

**Don't use a marketplace template.** Checked 2026-09-03: Railway's own
`postgis` template runs `postgis/postgis:16-master` — PostgreSQL **16**, and a
PostGIS pinned to nothing. The two PG17 templates (`postgis-17`,
`postgis-spatial-database`) declare **no volume at all**, so the database is
wiped on every redeploy. Create the service from an explicit image instead:

```bash
railway init --name conflict-coordinate
railway add --service postgres \
  --image postgis/postgis:16-3.4 \
  --variables POSTGRES_USER=conflict \
  --variables POSTGRES_PASSWORD="$(python3 -c 'import secrets;print(secrets.token_urlsafe(24))')" \
  --variables POSTGRES_DB=conflict \
  --variables PGDATA=/var/lib/postgresql/data/pgdata

railway service postgres          # link, or the next command panics
railway volume add -m /var/lib/postgresql/data
railway tcp-proxy create --port 5432 -s postgres   # needed to restore from your laptop
```

`16-3.4` matches local dev exactly, so the seed restore is same-major and
needs no cross-version handling. `PGDATA` must be a *subdirectory* of the
mount: the volume root is not empty, and initdb refuses to use it.

Two things that bite here:

- **Attach the volume before trusting any data.** A service created without
  one starts on ephemeral disk, and attaching a volume does not migrate it —
  it takes effect on the next deploy. Redeploy, then confirm persistence for
  real: write a row, `railway deployment redeploy`, read it back. Railway's
  reported volume usage rounds to `0.0 GB` at this size, so it proves nothing.
- The CLI's `railway volume list` printed "No volumes found" for a volume that
  existed and was mounted. `railway status` and the GraphQL API both showed it.

Volume default is 5 GB, comfortably over the ~750 MB seed plus WAL and growth.

## 2. API service

- Source: this repo, root directory `backend/`, Dockerfile build.
- Railway injects `PORT`; the image's CMD already reads it.
- The CMD runs `alembic upgrade head` before uvicorn, so every deploy
  migrates itself. A failed migration exits the container rather than serving
  against a schema the code no longer matches — Railway will restart-loop and
  the build logs name the failure. The cron service overrides the CMD, so
  migrations run from this service only.

```bash
railway add --service api --repo <owner>/conflict-coordinate --branch main
# rootDirectory is not settable via a CLI flag — use the API:
railway api 'mutation($sid:String!,$eid:String,$in:ServiceInstanceUpdateInput!){serviceInstanceUpdate(serviceId:$sid,environmentId:$eid,input:$in)}' \
  --raw-var sid=<serviceId> --raw-var eid=<environmentId> --var in='{"rootDirectory":"backend"}'
```

**`backend/railway.json` is what selects the Dockerfile.** Without it Railway's
autodetect (Railpack) claims the service and dies on "No start command
detected" — it never sees the CMD. Setting `dockerfilePath` through the API
does *not* displace it, and the `Builder` GraphQL enum has no `DOCKERFILE`
value; config-as-code does, and it lives in the repo rather than in dashboard
state. A successful build logs `load build definition from backend/Dockerfile`.

**Create the public domain only after a deployment has succeeded.** A domain
generated against a service with no successful deploy stays broken: DNS
resolves, the service is healthy, `targetPort` is right, and every request
still returns Railway's `{"status":"error","code":404,"message":"Application
not found"}` — with an empty `railway logs --http`, because the edge never
forwards anything. Setting `targetPort` and redeploying does not repair it.
Delete the domain and generate a new one; it binds immediately. Note this
changes the hostname, so set `VITE_API_URL` *after* the domain is known good.

Creating a service with `--repo` does **not** wire the GitHub deploy trigger,
so pushes will not build. Trigger one deploy explicitly with
`serviceInstanceDeployV2(serviceId:, environmentId:)`, and add a
`deploymentTriggerCreate` if you want auto-deploy on push.

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

Both are set in one call, alongside the same `rootDirectory`/`dockerfilePath`
as the API — `startCommand` is what overrides the image's CMD, which is why
migrations run from the API role only:

```bash
railway api 'mutation($sid:String!,$eid:String,$in:ServiceInstanceUpdateInput!){serviceInstanceUpdate(serviceId:$sid,environmentId:$eid,input:$in)}' \
  --raw-var sid=<ingestServiceId> --raw-var eid=<environmentId> \
  --var in='{"rootDirectory":"backend","dockerfilePath":"Dockerfile","startCommand":"python -m app.ingestion.runner","cronSchedule":"0 6 * * 2"}'
```

Deploying a cron service only *builds* it — the container does not run until
the schedule fires, so empty logs after a successful deploy are expected, not a
failure. To exercise the real cron path rather than the API's in-process route,
set `cronSchedule` to a couple of minutes ahead, redeploy, watch it fire, then
restore `0 6 * * 2`. Let the run finish before restoring: a redeploy kills it.
Set the variables with `railway variable set KEY --stdin --skip-deploys` so
secrets are never echoed into a terminal or transcript.

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

# Dump local data. Use a client matching the REMOTE major version. Both ends
# are PG16 (step 1 pins 16-3.4), so postgres:16-alpine is the right client —
# a dump written by a PG17 client cannot be read by a PG16 pg_restore.
# The client needs PostGIS in the server, not in itself, so plain
# `postgres:16-alpine` is enough — and it is multi-arch, while
# `postgis/postgis:17-3.5` publishes no arm64 build and will not run at all
# on an Apple Silicon machine.
#
# The three restrictions are all load-bearing (see below):
docker run --rm -e PGPASSWORD=conflict -v "$OUT:/out" --network host postgres:16-alpine \
  pg_dump -h 127.0.0.1 -p 5432 -U conflict -d conflict \
  --data-only --no-owner --no-privileges \
  --schema=public \
  --exclude-table-data=spatial_ref_sys \
  --exclude-table-data=alembic_version \
  -Fc -f /out/seed.dump

docker run --rm -v "$OUT:/out" --network host postgres:16-alpine \
  pg_restore -d 'postgresql://…railway…' --data-only --no-owner /out/seed.dump
```

Write `$OUT` to a path under `$HOME`. Colima mounts only `/Users/<you>` into
its VM, so a `-v` target anywhere else (`/tmp`, a scratch dir) silently lands
*inside the VM* and the host sees no file — with pg_dump still exiting 0.

Why each restriction is needed — all three were confirmed by restoring into a
scratch PostGIS container before any remote database existed:

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

## Live deployment (as of 2026-09-03)

Railway project `conflict-coordinate` (`cc9fe6e2-2583-445c-8c28-41104e62faaf`),
environment `production`:

| Service | What it is | Notes |
|---|---|---|
| `postgres` | `postgis/postgis:16-3.4` | PG 16.4 / PostGIS 3.4.3, 5 GB volume, TCP proxy for restores |
| `api` | repo `backend/`, Dockerfile | https://api-production-6e126.up.railway.app |
| `ingest` | same image, `startCommand` override | cron `0 6 * * 2` |

`DATABASE_URL` on both app services points at
`postgres.railway.internal:5432` over Railway's private network rather than
through the TCP proxy — the proxy exists for restores from a laptop, not for
service-to-service traffic.

Seeded 2026-09-03 from the local database: all 15 tables restored row-for-row
(1,088,691 `entity_mentions`, 844,365 `crisis_intensity_weekly`, 269,421
`crisis_events`), `alembic_version` at `0014`, 563 MB on disk. First
production ingest was `ingest_runs` id 10, `ok=true`, 8m31s, exercised through
the real cron rather than the API route.

Local secrets for this deployment live in `~/.conflict-deploy/` (`prod.env`,
`db.secret`, `crontab.backup`) — outside the repo, mode 600. The production
`ADMIN_TOKEN` is **not** the local dev one.

The interim local crontab from B6 was removed once the Railway cron was proven
(backup in `~/.conflict-deploy/crontab.backup`).

## Attribution

The deployed site carries ACLED, UCDP, GDELT and ReliefWeb attribution on the
About page. ACLED's Research tier is granted for academic use; keep the credit
prominent and the methodology page accurate.
