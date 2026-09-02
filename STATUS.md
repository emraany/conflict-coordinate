# Project status — 2026-09-02

Audited against the running local stack (colima + `conflict_db` + API on
:8000), not against the docs. Every figure below came from the database or a
live endpoint on that date; re-verify before acting on it (see the last
section).

---

## Snapshot

| | |
|---|---|
| Last ingest run | **2026-08-13** (ACLED cache + OAuth token mtimes) |
| Newest aggregate week in DB | **2026-08-01** |
| Age of the globe's data | **~4.5 weeks** (honest floor is ~10–14 days) |
| `/api/health` status | `"stale"` |
| Rows in `ingest_runs` | **0 — never written to** |
| Globe dots | 350 admin1 regions, 55 countries |
| Dots carrying a conflict name | 182 of 350 |
| Registry conflicts | 22, of which 13 have zero footprint cells |
| `crisis_events` | 245,321 rows, 143,871 already routed to a conflict |
| `entity_mentions` (NER) | 985,998 |
| DB size | 746 MB |
| Frontend typecheck | `tsc -b` clean |
| Deployed anywhere | no |

---

## What's wrong

### 1. The dot layer never runs actor-match routing — root cause of the naming holes

`route_event` has three tiers in priority order: actor match → admin1
footprint → country fallback. Both dot-naming call sites pass an empty actor
list, so tier 1 never fires:

```python
# backend/app/routers/globe.py:61  and  backend/app/routers/crises.py:155
conflict_id = route_event([], c.country_iso3, c.admin1_norm, idx)
#                         ^^ actor list — always empty
```

Meanwhile 143,871 events are *already* routed by actor match during ingest.
The classification work is done and unused.

**Belgorod — the largest dot on the globe at 2,049 events — is unnamed**,
despite its `crisis_actors` containing `Military Forces of Ukraine (2019-)`
and `registry.yaml` already carrying `"Military Forces of Ukraine%"` for
`russo-ukrainian-war`. Kursk likewise.

Passing the actor list gives **196 nameable dots vs 182 today** — 14 gained,
none lost, none changed. All 14 are Russia/Ukraine border regions that no
footprint cell and no country rule reaches:

| Region | Derived label | Events (4w) |
|---|---|---|
| russia-belgorod | Russo-Ukrainian War | 2,049 |
| russia-kursk | Russo-Ukrainian War | 185 |
| russia-krasnodar | Russo-Ukrainian War | 41 |
| russia-rostov | Russo-Ukrainian War | 27 |
| russia-bryansk | Russo-Ukrainian War | 23 |
| ukraine-poltava | Russo-Ukrainian War | 18 |
| *(+ 8 more at ≤8 events)* | Russo-Ukrainian War | |

> **Corrected 2026-09-02 (A1 implementation).** This table previously claimed
> **206** dots, from taking each dot's label off the modal conflict of its
> already-routed events. That number is not reachable: `crisis_events.conflict_id`
> is stamped at ingest and never re-derived, and 10 of those 24 extra dots are
> Iranian regions stamped `Israel–Hamas War (Gaza)` under the rule set that
> commit `6a57e5b` disowned when it split `israel-hezbollah-conflict` out on
> 2026-08-13 — the same day as the last ingest. Re-routing them under current
> rules also yields 196.

The 13 conflicts with **zero footprint cells**, matched only by country
fallback (so all 12 Syrian dots read "Syrian post-Assad transition" whether
or not that fits the oblast):

```
burkina-faso-insurgency   cameroon-internal-conflict   car-internal-conflict
colombia-armed-conflict   ethiopia-internal-conflict   haiti-gang-conflict
mali-insurgency           mexico-criminal-violence     niger-insurgency
pakistan-internal-conflict  somalia-conflict           south-sudan-conflict
syria-post-assad-transition
```

> **Corrected 2026-09-02 (A1 implementation).** This section previously
> proposed ~30–40 lines of `actor_patterns` as the fix. It is not one. Every
> one of the 13 already carries `country_patterns`, exactly one conflict claims
> each of those ISO3s, so tier 3 fires for all of them: **0 dots in those 13
> countries are unnamed.** An actor pattern there resolves to the same conflict
> tier 1 or tier 3 and would change no label. What the 12 Syrian dots sharing
> one name actually shows is that the registry holds a single Syrian conflict —
> a coverage question, not a pattern question, and Phase C's.

**No LLM is warranted anywhere in this.** The naming answer is in the
database; the conflict-vs-crime split (below) is legible from the same actor
strings; LLM-authored prose is barred by the neutrality rules; and
`CLAUDE.md` scopes LLM-API features out entirely.

### 2. It shows violent events, but calls itself a conflict map

```
BRA 26   MEX 21   NGA 20   COL 19   MMR 16   IND 16
UKR 16   RUS 16   YEM 15   SOM 14   IRN 12   SYR 12
```

Brazil outranks Ukraine on dot count. Iran, India, Bangladesh, Ecuador and
Honduras appear via riots and criminal violence. That is the documented
design, but it is the widest gap between what renders and what the project
claims to be. 168 of 350 dots carry no conflict name at all, so their dossier
section 03 is empty.

### 3. Nothing keeps the data fresh

The pipeline is code-complete and unscheduled. The freshness plumbing works —
it is correctly reporting `stale`. But `ingest_runs` has never been written
to (migration `0013` was authored the day after the last ingest), so **the
cron path and the run-recording path are both untested end to end**, as are
the two failure guards written specifically for unattended running.

### 4. You can't find anything on the globe

`pointsMerge={false}`, radius `0.34 + 0.1·log1p(events)`, click → dossier +
fly-to, so every dot is its own object. But at the default altitude of 2.4
with 350 dots the clusters collide, and there is **no search, no region list,
no filter** on the map page. Hex view is a density read, not a disambiguator.

### 5. Smaller seams

- **Two different 4-week numbers in one dossier.** Donetsk header says 1,786
  events; `stats.recent_4w_events` lower in the same panel says 2,260. Two
  computations, one label.
- **ReliefWeb section is thin** — 112 reports across 54 countries, roughly two
  per country, country-scoped rather than region-scoped. Not broken; will
  often look sparse.
- **Archive is genuinely old** — Rio's newest incident is 2026-03-27,
  Donetsk's 2026-06-30. Correctly labeled as an archive.

---

## Steps to completion (deployment excluded)

### Phase A — fix what is wrong (~half a day)

**A1. Make dot naming actor-aware.** ✅ **Done.** Pass the crisis's actor names
instead of `[]` at `globe.py:61` and `crises.py:155` — bounded by a new guard:
a tier-1 actor match only wins where the region's ISO3 is one the conflict
actually spans (`RoutingIndex.actor_scope`, populated from
`primary_iso3` + `secondary_iso3s` in `_load_routing_index`). Without it,
`syria-homs` became "Israel–Hezbollah conflict" and
`central-african-republic-vakaga` became "Sudanese Civil War" — the same
cross-front bleed `registry.yaml:106-110` warns about. Covered by
`backend/tests/test_routing.py`, the repo's first tests.
*Verified:* Belgorod and Kursk read "Russo-Ukrainian War"; named dots
**182 → 196**; the 350-label diff shows 14 gained, **0 changed, 0 lost**;
`/api/globe` and `/api/crises/{slug}` agree on every spot check. The guard also
un-routes 934 events in 18 regions that were being claimed across borders
(Kazakhstan, Norway, Belarus, Moldova, Romania, Lithuania as *Russo-Ukrainian
War*; Chad, Egypt, Eritrea as *Sudanese Civil War*) — that lands at the next
ingest, which re-runs the backfill.

**A2. ~~Add `actor_patterns` for the 13 conflicts listed above.~~** **Dropped —
it is a no-op.** See the correction in §1: all 13 already route by country
fallback and no dot in those countries is unnamed. The 154 dots still unnamed
are in countries with no registry conflict at all (Brazil 26, India 16, Iran 12,
Ecuador 9, Bangladesh 7, Kenya 6, Honduras 6, Afghanistan 6). That is Phase C.
Two things found while confirming this, both left alone: Nigeria's 8 unnamed
dots are *correctly* unnamed (their actors are `Rioters (Nigeria)`,
`Protesters (Nigeria)`, `Unidentified Armed Group (Nigeria)` — do not give
`nigeria-security-crisis` a `country_pattern`), and `actors_canon.yaml` aliases
are loaded but never become routing rules.

**A3. Reconcile the duplicate 4-week number.**
*Verify:* one number; both places agree on three spot-checked regions.

### Phase B — make it live locally (~half a day, then a week of waiting)

**B4. Run one full ingest end to end.**
*Verify:* an `ingest_runs` row lands with `ok=true` — the first ever;
`latest_agg_week` advances from 2026-08-01; `/api/health` flips `stale` → `ok`.

**B5. Exercise the two failure paths that have never executed.**
*Verify:* (a) force a source to raise → the run still completes, the error is
recorded, rollups still refresh; (b) delete 4 of 6 cached ACLED region files
→ `sweep_dropped` is skipped and zero crises are deleted.

**B6. Add the weekly crontab entry** (`0 6 * * 2`).
*Verify:* a week later, an `ingest_runs` row exists that nobody triggered.

Do B before C: the classifier in C should be built against fresh data.

### Phase C — fix the framing (~2–3 days; the real work)

**C7. Classify violence type per region** — `armed_conflict` /
`criminal_violence` / `unrest`, from actor names plus event-type mix
(`Al Shabaab` vs `Unidentified Gang (Haiti)` vs `Taxi Drivers`). Compute in
the rollup, store on `crises`.
*Verify:* hand-check 20 dots — Ukraine armed, Rio criminal, Iran unrest — and
confirm disagreements are genuinely ambiguous rather than wrong.

**C8. Surface it on the globe** — distinct colour family or a filter toggle.
*Verify:* Brazil and Ukraine no longer read as the same phenomenon; the 168
unnamed dots now convey something beyond "NO NAMED CONFLICT".

This closes the gap between "map of violent events" and "conflict map" — the
step that changes what the project is.

### Phase D — findability (~1 day)

**D9. Search box + region list on the map page.**
*Verify:* typing "Kharkiv" flies the globe there and opens the dossier.

### Phase E — still open from the roadmaps (optional)

**E10. `/conflicts/:slug` as a real page.** Conflict detail is a panel with
local state; `App.tsx:25` routes `/conflicts/anything` to the index, so there
are no shareable conflict URLs. Pages-roadmap item 3, the only one of five
not done.

**E11. Forecasting.** Last open ML-roadmap item; NER, actor graph and
clustering are built. Summarization was deliberately scoped out by the
neutrality rules.

**Definition of done:** A + B + C. After those the site is accurate,
self-updating, and says true things about what it shows. D makes it usable;
E is portfolio polish.

*Least reliable estimate here is Phase C. Classification quality depends on
how consistent ACLED's actor naming is across all 55 countries, and only five
were spot-checked.*

---

## How to work through it

**Batches — one plan-mode session each:**

| Batch | Contents | Notes |
|---|---|---|
| 1 | **Phase A** (A1–A3) | One plan. All three share the routing/naming code and one verification (the 350-label diff); splitting means running that diff three times. |
| 2 | **Phase B** (B4–B6) | **No plan mode needed** — running commands and watching. B5 is the only thinking part, and that's a conversation. |
| 3 | **Phase C** (C7–C8) | One plan, two commits. Plan together (how you classify determines what the UI can show); build C7, verify the 20 hand-checks, *then* C8. |
| 4 | **Phase D** (D9) | One small plan. |
| 5 | E10, E11 | Separately, whenever. |

**Prompt to open a planning session after a context clear:**

> Read `STATUS.md` and `CLAUDE.md`. Plan Phase A only. The numbers in
> STATUS.md are a 2026-09-02 snapshot — verify the claims against the live
> database and code before planning, don't trust the doc.

That last clause matters: a plan built on a stale snapshot will be subtly
wrong.

**Rhythm:**

- **Don't clear between planning and implementing the same phase** — the
  plan's value is the context gathered while writing it.
- **Clear between phases**, when the next one touches different code.
- **Definitely clear before Phase C.** A and B leave a lot of ingest output
  and label diffs in context that C doesn't need, and C most deserves a clean
  head.

---

## Deployment (excluded from the plan above)

Plan phases 1–3 landed (`9b082c2`, `1e18206`, `b8eab47`): `backend/Dockerfile`,
`frontend/vercel.json`, the DB-URL scheme validator, `PRODUCTION` /
`ADMIN_TOKEN` fail-fast, per-source failure isolation, the `sweep_dropped`
guard, `ingest_runs`, and the real `/api/health`.

Not started: Railway (PostGIS ≥2 GB volume, API, cron `0 6 * * 2`),
`alembic upgrade head` + `pg_dump`/`pg_restore` of the 746 MB DB (PG16 → PG17,
use a `postgis/postgis:17-3.5` client), the Vercel project and
`VITE_API_URL`, and an uptime monitor on `/api/health`. See `DEPLOY.md`.

Two gaps the deploy plan called for and didn't get:

- **No rate limiting** anywhere in `backend/app/`. `/api/activity` clamps
  `limit` at 1000, but nothing throttles requests. A public URL with no auth
  and no throttle.
- **Nothing runs migrations on deploy.** The Dockerfile `CMD` is uvicorn only
  — fine for launch, a footgun on every future migration.

---

## Data sources

For the conflict-vs-violence gap, **no new source is needed** — the fix is
classification over actor names and event types already stored.

Worth adding, by payoff:

- **ACLED CAST** — monthly conflict forecasts on credentials already held.
  Feeds E11 without a new data relationship.
- **ACAPS INFORM Severity Index** — free API, per-crisis severity updated
  monthly. A neutral, citable "how bad is this" that raw event counts cannot
  give; directly addresses Brazil-outranks-Ukraine.
- **IOM DTM / UNHCR** — displacement; a severity dimension independent of
  fatalities.

Skip: GDELT DOC 2.0 (already present as a signal), CFR Global Conflict
Tracker (scraping), IISS Armed Conflict Survey (paywalled).
`UCDP_CANDIDATE_VERSIONS` is already populated (`26.0.1`–`26.0.5`).

*API terms for CAST and ACAPS were not verified against their live docs.*

---

## Reproducing these numbers

```bash
docker compose up -d
cd backend && uv run uvicorn app.main:app --port 8000

curl -s localhost:8000/api/health | python3 -m json.tool
curl -s localhost:8000/api/globe | python3 -c "import json,sys;print(len(json.load(sys.stdin)))"

docker exec conflict_db psql -U conflict -d conflict \
  -c "select max(latest_agg_week), count(*) filter (where violence_4w_events>=5 or violence_4w_fatalities>=5) from crises;" \
  -c "select count(*) from ingest_runs;" \
  -c "select count(*) filter (where conflict_id is not null), count(*) from crisis_events;"
```
