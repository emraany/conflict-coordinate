# Project status — 2026-09-02 (Phases A and B complete)

Audited against the running local stack (colima + `conflict_db` + API on
:8000), not against the docs. Every figure below came from the database or a
live endpoint on that date; re-verify before acting on it (see the last
section).

**Phase A** (actor-aware dot naming, one four-week number) and **Phase B**
(a real recorded ingest, both failure guards exercised, weekly cron) are
done. The figures below are post-ingest and differ substantially from the
pre-Phase-A audit — most visibly the dot count, which fell 350 → 311 as the
window advanced three weeks. **Phase C is next.**

---

## Snapshot

| | before (audit) | now |
|---|---|---|
| Last ingest run | 2026-08-13 (inferred from file mtimes) | **2026-09-02, recorded, `ok=true`** |
| Newest aggregate week in DB | 2026-08-01 | **2026-08-22** |
| Newest event of any kind | 2026-08-14 | **2026-09-02** (GDELT, same-day) |
| `/api/health` status | `"stale"` | **`"ok"`** |
| Rows in `ingest_runs` | 0 — never written to | **2** (one failed, one ok) |
| Scheduled ingest | none | **crontab, Tuesdays 06:00 UTC** |
| Globe dots | 350 regions, 55 countries | **311 regions, 53 countries** |
| Dots carrying a conflict name | 182 of 350 (52%) | **190 of 311 (61%)** |
| Registry conflicts | 22, 13 with zero footprint cells | unchanged |
| `crisis_events` | 245,321 rows, 143,871 routed | **268,029 rows, 153,889 routed** |
| Events routed across a border | 2,792 | **0** |
| `entity_mentions` (NER) | 985,998 | **1,038,243** |
| DB size | 746 MB | **750 MB** |
| Backend tests | none in repo | **5, passing** |
| Frontend typecheck | `tsc -b` clean | clean |
| Deployed anywhere | no | no |

The largest dot on the globe is now `russia-belgorod` (1,701 events),
correctly reading *Russo-Ukrainian War*. Before Phase A it was unnamed.

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
BRA 26   NGA 23   MEX 20   COL 20   UKR 16   SOM 15
YEM 14   RUS 12   SDN 12   SYR 11   MMR 10   IRN  9
```

Brazil still outranks Ukraine on dot count. Iran, India, Ecuador and Honduras
appear via riots and criminal violence. That is the documented design, but it
is the widest gap between what renders and what the project claims to be.
**121 of 311 dots carry no conflict name** (was 168 of 350), so their dossier
section 03 is empty. Phase A closed the share that was a routing bug; what is
left is genuine registry coverage:

```
BRA 26   NGA 11   IRN 9   IRQ 9   ECU 8   HND 7   KEN 7   IND 6
```

The largest unnamed dots are `brazil-rio-de-janeiro` (135 events),
`brazil-bahia` (108), `brazil-pernambuco` (100), `ecuador-guayas` (88). None
of those countries has a registry conflict at all — that is Phase C's
subject, and no amount of routing work reaches it.

### 3. ~~Nothing keeps the data fresh~~ — resolved in Phase B

The pipeline now runs, records itself, and is scheduled. Both failure guards
have executed against real data — one of them without being asked to. Detail
under Phase B below. Two live bugs surfaced only because the ingest was
finally run end to end, and both are fixed:

- **GDELT had been dead in every run.** `data.gdeltproject.org` answers http
  with a 301 to https and `httpx` does not follow redirects by default, so
  the source failed on its first call every time. It now attaches events
  again, and the newest event in the DB moved 2026-08-14 → same-day.
- **Stale conflict stamps were never cleared.** `backfill` promised
  "NULL on miss" but a miss only counted an orphan, so events kept a
  `conflict_id` no current rule justified. 2,942 stamps were cleared on the
  verifying run.

### 4. You can't find anything on the globe

`pointsMerge={false}`, radius `0.34 + 0.1·log1p(events)`, click → dossier +
fly-to, so every dot is its own object. But at the default altitude of 2.4
with 311 dots the clusters still collide, and there is **no search, no region
list, no filter** on the map page. Hex view is a density read, not a
disambiguator.

### 5. Smaller seams

- ~~**Two different 4-week numbers in one dossier.**~~ Fixed in Phase A. The
  header, the `BREAKDOWN` bars and `stats.recent_4w_events` now agree by
  construction; verified equal across all 311 dots. The audit misread which
  two numbers collided — see A3 below.
- **ReliefWeb section is thin** — 185 reports across 53 countries, roughly
  three per country, country-scoped rather than region-scoped. Not broken;
  will often look sparse.
- **Archive is still genuinely old** — Rio's newest incident with prose is
  2026-03-27, Donetsk's 2026-07-31. Correctly labeled as an archive; the
  current layer is the aggregates, which are 11 days old.
- **Nothing reaps an interrupted run.** A killed ingest leaves an
  `ingest_runs` row with `finished_at` NULL forever. `/api/health` is
  unaffected (it keys off the last *successful* run), so this is cosmetic —
  but a long-running deployment will accumulate them.

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

### Phase B — make it live locally ✅ **Done 2026-09-02**

**B4. Run one full ingest end to end.** ✅ It took two runs.

The first (`ingest_runs` id 2, 11m27s) came back **`ok=false`** — correctly.
`ok = error is None and not source_failed`, and GDELT had failed on a 301
redirect. That is the run-recording path working as designed: a run that
half-worked must not read as healthy. After fixing GDELT, run id 3 (10m38s)
is the **first `ok=true` ingest in the project's history**.
*Verified:* `latest_agg_week` 2026-08-01 → **2026-08-22**; `/api/health`
`stale` → **`ok`**; +22,708 events, +52,245 NER mentions; newest event now
same-day via GDELT.

**Dots fell 350 → 311, and that is aging, not loss.** 80 dots left the set,
41 joined. All 80 still exist as rows with at most 4 events and 4 fatalities
— just under the `>=5` threshold — and **zero were deleted**. No surviving
dot changed its label, so the Phase A guard is stable across a re-ingest.

**B5. Exercise the two failure paths.** ✅ Both fired; one was never forced.

- **(b) sweep guard — exercised live, unplanned.** ACLED's `asia-pacific`
  region genuinely failed to resolve an xlsx URL that day, so
  `fetch_complete = regions_ok == len(REGIONS)` went False on its own and the
  run recorded `sweep_skipped: "incomplete fetch"`. Zero crises deleted.
  No cache files needed deleting to simulate it. Note there are **two**
  brakes, not one: the runner's `fetch_complete` gate, and a second
  independent cap inside `sweep_dropped` that refuses any sweep exceeding
  `SWEEP_MAX_DELETE_FRACTION` of candidates.
- **(a) per-source isolation — half live, half injected.** GDELT's real
  failure proved the run completes, the error lands in
  `ingest_runs.result`, and the whole tail still refreshes. But GDELT is
  *last* in `SOURCES`, so it could not show that a later source still runs.
  Injecting a raising stub ahead of `FixtureSource` closed that: the stub's
  error was recorded, `fixture` ran after it, and dot rollups, routing and
  NER all completed. `/api/health` then read **`degraded`** — last run
  failed, prior success intact — a third status value the audit never saw.
  The two synthetic rows were deleted afterwards so the operational log holds
  only real runs.

**B6. Add the weekly crontab entry** ✅ Installed:

```
0 6 * * 2 cd /Users/emraan/Desktop/Conflict/backend && \
  /opt/homebrew/bin/uv run python -m app.ingestion.runner \
  >> /Users/emraan/.conflict-ingest.log 2>&1
```

Rather than wait a week for the verify, the command was run under `env -i`
(cron's bare environment, no PATH or shell profile): config loads with
credentials and the runner imports. `.env` resolves from `__file__`, so the
working directory cannot break credentials.

*Still unverified, and the likely failure mode:* on modern macOS,
`/usr/sbin/cron` needs **Full Disk Access** to read anything under
`~/Desktop`. The `env -i` test ran as the user and inherited the terminal's
grant, so it does not prove cron itself can reach the repo. **If next
Tuesday leaves no new `ingest_runs` row, that is the cause** — System
Settings → Privacy & Security → Full Disk Access → add `/usr/sbin/cron`.
Undo the schedule entirely with `crontab -r`.

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
| ~~1~~ | ~~**Phase A** (A1–A3)~~ | ✅ Done. A2 turned out to be a no-op; the label diff caught two cross-border regressions before they shipped. |
| ~~2~~ | ~~**Phase B** (B4–B6)~~ | ✅ Done. No plan mode was needed, as predicted. Running it surfaced two live bugs the code review could not have. |
| **3** | **Phase C** (C7–C8) ← **next** | One plan, two commits. Plan together (how you classify determines what the UI can show); build C7, verify the 20 hand-checks, *then* C8. |
| 4 | **Phase D** (D9) | One small plan. |
| 5 | E10, E11 | Separately, whenever. |

**Prompt to open the next planning session after a context clear:**

> Read `STATUS.md` and `CLAUDE.md`. Plan Phase C only. The numbers in
> STATUS.md are a 2026-09-02 post-ingest snapshot — verify the claims against
> the live database and code before planning, don't trust the doc.

That last clause matters, and Phases A and B both proved it: the audit's
A1 target (206 named dots) was unreachable, its A2 was a no-op, and its A3
named the wrong pair of numbers. Every one of those was caught by checking
the doc against the database before writing code.

**One caveat specific to Phase C.** C7's verify ("hand-check 20 dots") was
written against a 350-dot globe. The set is now 311 and its composition
shifted — 80 out, 41 in — so pick the 20 fresh rather than reusing any list.
The four regions the audit named as examples (Ukraine armed, Rio criminal,
Iran unrest) are all still dots.

**Rhythm:**

- **Don't clear between planning and implementing the same phase** — the
  plan's value is the context gathered while writing it.
- **Clear between phases**, when the next one touches different code.
- **Definitely clear before Phase C.** A and B left a lot of ingest output and
  label diffs in context that C doesn't need, and C most deserves a clean
  head. That clear is due now.

---

## Deployment (excluded from the plan above)

Plan phases 1–3 landed (`9b082c2`, `1e18206`, `b8eab47`): `backend/Dockerfile`,
`frontend/vercel.json`, the DB-URL scheme validator, `PRODUCTION` /
`ADMIN_TOKEN` fail-fast, per-source failure isolation, the `sweep_dropped`
guard, `ingest_runs`, and the real `/api/health`.

Not started: Railway (PostGIS ≥2 GB volume, API, cron `0 6 * * 2`),
`alembic upgrade head` + `pg_dump`/`pg_restore` of the 750 MB DB (PG16 → PG17,
use a `postgis/postgis:17-3.5` client), the Vercel project and
`VITE_API_URL`, and an uptime monitor on `/api/health`. See `DEPLOY.md`.

The local crontab from B6 is an **interim** measure and should be removed
(`crontab -r`) once the Railway cron service runs — otherwise two schedulers
ingest into two databases. `/api/health` is now worth pointing an uptime
monitor at: it distinguishes `ok`, `degraded` (last run failed, earlier
success stands) and `stale` (no success within `STATUS_STALE_DAYS`).

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
cd backend && uv run uvicorn app.main:app --reload --port 8000
cd ../frontend && npm run dev        # :5173

curl -s localhost:8000/api/health | python3 -m json.tool

# dots, and how many carry a conflict name
curl -s localhost:8000/api/globe | python3 -c "
import json,sys; d=json.load(sys.stdin)
print(len(d), 'dots,', sum(1 for x in d if x.get('conflict')), 'named')"

# the three four-week numbers must all agree (A3)
curl -s localhost:8000/api/crises/ukraine-donetsk | python3 -c "
import json,sys; d=json.load(sys.stdin)
print(d['violence_4w_events'], sum(a['events'] for a in d['activity']), d['stats']['recent_4w_events'])"

cd ../backend && uv run pytest -q          # 5 tests, routing guard
crontab -l                                  # the weekly ingest

docker exec conflict_db psql -U conflict -d conflict \
  -c "select id, ok, trigger, finished_at from ingest_runs order by id;" \
  -c "select max(week_start) from crisis_intensity_weekly;" \
  -c "select count(*) filter (where conflict_id is not null), count(*) from crisis_events;"

# must return 0 — no event routed outside its conflict's own geography
docker exec conflict_db psql -U conflict -d conflict -c "
select count(*) from crisis_events e
  join crises c on c.id = e.crisis_id
  join conflicts cf on cf.id = e.conflict_id
where c.country_iso3 <> cf.primary_iso3
  and not (c.country_iso3 = any(cf.secondary_iso3s));"
```

**Re-running the ingest by hand** (~11 minutes, network-bound):

```bash
cd backend && uv run python -m app.ingestion.runner
```

It is idempotent. Do **not** run `backfill_routing --commit` on its own to
force a re-route: it also rewrites conflict centroids and `intensity_4w_*`,
and flips `crises.legacy` unless `--no-legacy-flip` is passed. The ingest
tail calls it correctly already.
