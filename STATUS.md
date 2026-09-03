# Project status — 2026-09-03 (Phases A–D complete; deployed)

Audited against the running local stack (colima + `conflict_db` + API on
:8000), not against the docs. Every figure below came from the database or a
live endpoint on that date; re-verify before acting on it (see the last
section).

**Phase A** (actor-aware dot naming, one four-week number), **Phase B**
(a real recorded ingest, both failure guards exercised, weekly cron),
**Phase C** (violence classification, and the globe filter that shows it) and
**Phase D** (the region index — search by name instead of by eye) are done.
The dot count moved twice: 350 → 311 as the window advanced three weeks
in Phase B, then 311 → 293 when Phase C fixed a rollup bug that had been
keeping regions on the globe on month-old counts. **The site is deployed
and public: https://conflict-coordinate.vercel.app**

## What's left

Nothing is blocking. Everything below is optional or needs a browser.

| | Item | Needs |
|---|---|---|
| 1 | **Uptime monitor** on `/api/health` | a signup — catches a stalled pipeline that still returns HTTP 200, otherwise invisible for a week |
| 2 | **Throttle-key check** | a second network (phone hotspot); one machine cannot tell a per-client bucket from a shared one |
| 3 | **Railway deploy trigger** | connecting GitHub to Railway; until then backend deploys are manual |
| 4 | **E10 — `/conflicts/:slug` as a real page** | nothing. Worth the most now that there is a URL to share |
| 5 | **E11 — forecasting** | nothing. Last open ML-roadmap item |
| 6 | **Registry coverage** | 38 unnamed dots classed `armed_conflict` (BRA 26, NGA 11, IRQ 9, ECU 8…). No routing work reaches these — the registry has no conflict for those countries |

1–3 are operational and small. 4 and 5 are portfolio polish. 6 is the only
one that would change what the map *says*, and it is editorial work rather
than engineering: writing registry entries, each with a citation.

*All Phase C verifications are closed, including the confirming ingest
(`ingest_runs` id 7, `ok=true`, 7m07s). Every figure below came from the
database after that run. Phase D touched no data — it is frontend only, and
its own verification is noted under D9.*

---

## Snapshot

| | before (audit) | now |
|---|---|---|
| Last ingest run | 2026-08-13 (inferred from file mtimes) | **2026-09-02, recorded, `ok=true`** |
| Newest aggregate week in DB | 2026-08-01 | **2026-08-22** |
| Newest event of any kind | 2026-08-14 | **2026-09-02** (GDELT, same-day) |
| `/api/health` status | `"stale"` | **`"ok"`** |
| Rows in `ingest_runs` | 0 — never written to | **4** (two ok, one failed, one interrupted) |
| Scheduled ingest | none | **crontab, Tuesdays 06:00 UTC** |
| Globe dots | 350 regions, 55 countries | **293 regions, 53 countries** |
| Dots carrying a conflict name | 182 of 350 (52%) | **189 of 293 (65%)** |
| Dots stating what kind of violence | none — the field didn't exist | **293: 198 armed, 74 criminal, 15 unrest, 6 unclear** |
| Registry conflicts | 22, 13 with zero footprint cells | unchanged |
| `crisis_events` | 245,321 rows, 143,871 routed | **268,029 rows, 153,889 routed** |
| Events routed across a border | 2,792 | **0** |
| `entity_mentions` (NER) | 985,998 | **1,038,243** |
| DB size | 746 MB | **750 MB** |
| Backend tests | none in repo | **11, passing** |
| Frontend typecheck | `tsc -b` clean | clean |
| Finding a named region on the globe | by eye only | **searchable — name, country, ISO3, conflict** |
| Deployed anywhere | no | **yes — [conflict-coordinate.vercel.app](https://conflict-coordinate.vercel.app)** |

The largest dot on the globe is now `russia-belgorod` (1,701 events),
correctly reading *Russo-Ukrainian War*. Before Phase A it was unnamed.

---

## What's wrong

### 1. ~~The dot layer never runs actor-match routing~~ — fixed in Phase A

`route_event` has three tiers in priority order: actor match → admin1
footprint → country fallback. Both dot-naming call sites used to pass an empty
actor list, so tier 1 never fired. Both now pass the real bag
(`globe.py:65`, `crises.py:141`), which is what took named dots to 65%.
The rest of this section is kept as the diagnosis that produced the fix.

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

### 2. ~~It shows violent events, but calls itself a conflict map~~ — addressed in Phase C

```
BRA 26   NGA 23   MEX 20   COL 20   UKR 16   SOM 15
YEM 14   SDN 12   RUS 11   SYR 11   MLI  9   MMR  9
```

Brazil still outranks Ukraine on dot count, and always will: a dot is a
region with violence, and Brazil has more regions with violence than Ukraine
has regions. What changed is that the map no longer implies they are the same
phenomenon. Every dot now states its kind, and Brazil's 26 read
**criminal violence** while Ukraine's 16 read **armed conflict**.

Iran's and India's appearances were mostly the stale-rollup bug (§6), not
riots: nine Iranian dots and `india-bihar` were standing on month-old counts
with nothing violent in the current window at all.

**104 of 293 dots still carry no conflict name**, so their dossier section 03
is empty — but 66 of those 104 now say something about themselves anyway
(48 criminal, 15 unrest, 3 unclear). The real registry-coverage gap is the
remaining **38 unnamed dots classed armed_conflict**:

```
BRA 26   NGA 11   IRQ 9   ECU 8   HND 6   KEN 6   COD 4   GTM 3
```

The largest unnamed dots are `brazil-rio-de-janeiro` (135 events),
`brazil-bahia` (108), `brazil-pernambuco` (100), `ecuador-guayas` (88) — all
four now labelled criminal violence, which is what they are. None of those
countries has a registry conflict, and no routing work reaches that.

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

### 4. ~~You can't find anything on the globe~~ — fixed in Phase D

`pointsMerge={false}`, radius `0.34 + 0.1·log1p(events)`, click → dossier +
fly-to, so every dot is its own object. At the default altitude of 2.4 with
293 dots the clusters still collide, and hex view is a density read, not a
disambiguator. Phase C added the first filter — by kind of violence, which
cuts the globe to 198 / 74 / 15 — but a filter narrows; it does not locate.
Phase D added the region index: a text way in that searches all 293 and puts
the camera and the dossier where a click would.

### 5. Smaller seams

- ~~**Two different 4-week numbers in one dossier.**~~ Fixed in Phase A. The
  header, the `BREAKDOWN` bars and `stats.recent_4w_events` now agree by
  construction; verified equal across all dots. The audit misread which
  two numbers collided — see A3 below.
- **ReliefWeb section is thin** — 185 reports across 53 countries, roughly
  three per country, country-scoped rather than region-scoped. Not broken;
  will often look sparse.
- **Archive is still genuinely old** — Rio's newest incident with prose is
  2026-03-27, Donetsk's 2026-07-31. Correctly labeled as an archive; the
  current layer is the aggregates, which are 11 days old.
- ~~**Nothing reaps an interrupted run.**~~ Fixed 2026-09-03. A killed ingest
  left an `ingest_runs` row with `finished_at` NULL forever. `_start_ingest_run`
  now closes out any open row older than `ABANDONED_RUN_HOURS` (24) before
  opening its own, marking it `ok=false` with an explicit error. Bounded by
  age rather than done unconditionally, so a manual `POST /api/ingest/run`
  fired while the weekly cron is mid-flight doesn't declare the cron dead —
  the longest run on record is 11m27s. *Verified* against the live table in a
  rolled-back transaction: a synthetic 30h-old open row was reaped, a
  10-minute-old one was not. Row id 6 (the interrupted Phase C run) was 20.7h
  old at the time and will be closed by the next ingest.

### 6. ~~Dots stood on counts no current week justified~~ — fixed in Phase C

`_refresh_crisis_activity_rollups` updated only crises that appeared in its
aggregate CTE, and zeroed only those with *no* weekly rows at all in the
window. A region whose violence stopped but whose protests continued
satisfied neither test, so it kept a month-old violent count and stayed on
the globe. 18 of 311 dots were in that state — nine Iranian, plus
`india-bihar`, `myanmar-yangon` and `afghanistan-panjshir`; their dossiers
read "4 weeks to 2026-07-25" against an aggregate frontier of 2026-08-22.
One statement now recomputes every crisis over a LEFT JOIN. Globe: 311 → 293.

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

### Phase C — fix the framing ✅ **Done 2026-09-02**

**C0. Stale rollups.** ✅ Found while checking the doc against the database,
before writing any classifier — 18 of the 311 dots had no qualifying violence
in the current window at all. Detail in §6 above. Fixed first, so nothing was
classified off a month-old count.

**C7. Classify violence type per region.** ✅ `app/conflicts/violence_class.py`
— pure, no SQLAlchemy, like `routing.py` — plus migration `0014`
(`crises.violence_class`, `violence_class_basis`) and a `_classify_violence`
step in the ingest tail beside the rollup.

The audit's premise ("actor names plus event-type mix") was half right. Mix
carries nothing on the criminal/armed axis: **80% of Rio's current window is
Battles**, because ACLED codes a gang-versus-police shootout as
`Battles / Armed clash`, exactly like a frontline engagement. Only the actor
names separate them, and two ACLED conventions defeat the obvious patterns —
state police are filed as `Military Forces of Brazil (2023-) Military Police`,
and `Unidentified Armed Group (X)` is a filler for an unknown perpetrator.
Both are pinned by tests. Criminal actors outrank state forces in the decision
order, because armies are deployed against cartels — that is what keeps
Sinaloa from reading as a war.

`SUB_EVENT_TYPE` was evaluated and **deliberately deferred**: it is in the
cached xlsx and would sharpen unrest (`Mob violence` vs `Violent
demonstration`), but Rio and Donetsk both show `Armed clash`, so it does not
touch the axis that mattered. Not worth a migration and a re-ingest.

*Verified:* 293 dots — **198 armed, 74 criminal, 15 unrest, 6 unclear**.
Hand-checked 20 spanning all four classes: 16 clean, 4 arguable, none wrong.
`palestine-west-bank` reads armed off Israeli forces though 85% of its window
is riots; `colombia-atlantico` reads criminal off Gulf Clan, which ACLED types
a political militia; `iraq-al-basrah` and `nigeria-lagos` fall to unclear just
under the battle-share threshold. Every label carries a derived basis string
quoting its own evidence, so a reader sees those tensions rather than taking
the label on faith. 11 backend tests pass.

**C8. Surface it on the globe.** ✅ Colour stays lethality and size stays
event count — one variable per channel is why the legend is readable — so the
class reads through filtering and text. A chip row above the existing globe
controls filters to armed / criminal / unrest, and dots, hex bins and pulse
rings all follow it. Tooltip and dossier header carry a bracketed class; the
dossier chip's `title` is the basis. `UNCLASSIFIED` renders dim beside
`NO NAMED CONFLICT` — the two things the map declines to guess at.
*Verified:* `tsc -b` and `npm run build` clean; `/api/globe` and
`/api/crises/{slug}` both carry the class and its basis.

**Confirmed end to end** by `ingest_runs` id 7 (`ok=true`, 7m07s). The dot
set was identical — none left, none joined — and exactly **two** dots changed
class, both `unclear` → `armed_conflict`: `colombia-santander` and
`iraq-maysan`, each because the lagged event source attached new incidents
that put a national military in its actor bag for the first time. **Zero dots
flipped class with an unchanged actor bag**, which is the property that
matters: the label is a function of its evidence, not of when it ran.

The one earlier attempt at this run was interrupted a minute in, before it
reached the tail; it wrote nothing and left the orphan `ingest_runs` row
noted in §5.

### Phase D — findability ✅ **Done 2026-09-02**

**D9. Search box + region list on the map page.** ✅
`frontend/src/components/RegionIndex.tsx`, one commit (`f9c6b41`). A
collapsible panel at the globe's top right — the only free screen edge —
listing all 293 regions in the order `/api/globe` already returns them
(four-week events, descending), searchable by region name, country, ISO3 and
conflict name. Rows call the same handler a dot click does, so a hit inherits
the existing fly-to and dossier for free.

Smaller than it looked, for two reasons found while planning: the whole
293-dot payload is already client-side, so this needed **no backend change of
any kind** — no endpoint, no query, no index, no migration; and the fly-to
was already an effect on the `selectedSlug` prop rather than on the click, so
anything that sets it moves the camera. The only real work was lifting
`classFilter` out of `Globe` into `MapPage` so the list and the globe agree
on what is filtered.

Two deliberate behaviours: the list searches all 293 regardless of the active
class filter, and selecting a hit the filter is hiding resets the chips to
`ALL` — searching "Rio" under `ARMED` and getting nothing would read as "Rio
has no violence", which is false. And dashes are folded before matching:
region names are all ASCII, but conflict names are not, so a typed hyphen
would otherwise miss `Israel–Hamas War (Gaza)`.

*Verified:* `tsc -b` and `npm run build` clean. The match function run over
the live `/api/globe` payload: `Kharkiv` → exactly one hit
(`ukraine-kharkiv`, 753 events, armed conflict), `russo` → 24 dots carrying
*Russo-Ukrainian War*, ASCII `Israel-Hamas` → the two en-dashed Gaza-war
dots, `Rio` → 4 including `brazil-rio-de-janeiro` (criminal, 135 events),
nonsense → 0. Rendered against the running app: the panel clears the legend,
the chip stack and the hex caveat, and rows read on-aesthetic.

**Driven by hand afterwards, and it found two things the checks above could
not** (`8213b4c`):

- **The arrow keys did nothing.** The handler was bound to the search input,
  so it only ran while that input held focus — and clicking a row moves focus
  to that row's `<button>`, which is exactly when you next want to press down.
  The plan had ruled out a document listener as "a new class of thing"; that
  was the wrong call, and it is one now, scoped to the panel being open, no
  modifier held, and focus not outside the panel. Enter defers to a focused
  button, which already turns Enter into its own click.
- **Flying to a region is not the same as finding it.** `selectedSlug` only
  ever moved the camera (`Globe.tsx:382`), so arriving at Rio de Janeiro put
  you in front of 26 Brazilian dots with nothing marking which one you asked
  for. D9's premise — "rows behave exactly like clicking a dot" — was true and
  still insufficient: clicking a dot tells you which one you clicked, and
  searching does not. The selected region now carries a slow ring in bone,
  deliberately off the lethality ramp so it cannot be misread as a severity,
  drawn from the unfiltered dot list and shown in hex view too.

**Confirmed on screen by the author, 2026-09-03** — both fixes behave as
described. Collapse persistence and the filter-reset check were not part of
that pass and remain unconfirmed; the sandbox grants browsers read-only, so
they still need a human at the keyboard.

*Deferred, as decisions rather than oversights:* alias matching — the 153
rows in `admin1_aliases` ("Halab"→Aleppo, "Dacca"→Dhaka) would need a backend
field, and bolt on later without reworking any of this; and a shareable URL
for a selected region, which is E10's problem.

### Phase E — still open from the roadmaps (optional)

**E10. `/conflicts/:slug` as a real page.** Conflict detail is a panel with
local state; `App.tsx:25` routes `/conflicts/anything` to the index, so there
are no shareable conflict URLs. Pages-roadmap item 3, the only one of five
not done.

**E11. Forecasting.** Last open ML-roadmap item; NER, actor graph and
clustering are built. Summarization was deliberately scoped out by the
neutrality rules.

**Definition of done:** A + B + C — **met**, and D on top of it. The site is
accurate, self-updating, says true things about what it shows, and can now be
navigated by name rather than by eye. E is portfolio polish.

*The Phase C estimate was the least reliable one here, and it held up better
than expected: ACLED's actor naming turned out consistent enough across all
53 countries that a lexicon over it works. The residual risk is not naming
consistency but staleness — the actor bag comes from an archive ACLED
embargoes ~12 months, while the event mix is the current window. A region
whose war ended last year still carries its combatants. Every basis string
names both inputs so that tension is visible.*

---

## How to work through it

**Batches — one plan-mode session each:**

| Batch | Contents | Notes |
|---|---|---|
| ~~1~~ | ~~**Phase A** (A1–A3)~~ | ✅ Done. A2 turned out to be a no-op; the label diff caught two cross-border regressions before they shipped. |
| ~~2~~ | ~~**Phase B** (B4–B6)~~ | ✅ Done. No plan mode was needed, as predicted. Running it surfaced two live bugs the code review could not have. |
| ~~3~~ | ~~**Phase C** (C7–C8)~~ | ✅ Done in three commits, not two: checking the doc against the database first turned up the stale-rollup bug, which had to land before anything was classified. |
| ~~4~~ | ~~**Phase D** (D9)~~ | ✅ Done in one commit, no backend change. The plan was right that it was small, and right about why. |
| ~~5~~ | ~~**Pre-deploy hardening**~~ | ✅ Done 2026-09-03, no plan mode needed. Rate limiting, migrations on deploy, and the abandoned-run reaper. Tests 11 → 16. |
| ~~6~~ | ~~**Deploy**~~ | ✅ Done 2026-09-03. Railway (Postgres + API + weekly cron) and Vercel. The site is public. See below. |
| 7 | E10, E11 ← **next** | Optional, and worth splitting — they share no code. E10 is now worth more: there is a shareable URL. |

**Prompt to open the next planning session after a context clear:**

> Read `STATUS.md` and `CLAUDE.md`. Plan Phase E only. The numbers in
> STATUS.md are a 2026-09-02 snapshot — verify the claims against the live
> database and code before planning, don't trust the doc.

That last clause matters, and all four phases have now proved it: the
audit's A1 target (206 named dots) was unreachable, its A2 was a no-op, its
A3 named the wrong pair of numbers, and its C7 premise — classify from actor
names *plus event-type mix* — was half wrong, because the mix says nothing
about the criminal/armed split. Phase C also found a bug worth 18 dots that
no amount of reading the doc would have surfaced. Every one of those was
caught by checking the doc against the database before writing code.

**Rhythm:**

- **Don't clear between planning and implementing the same phase** — the
  plan's value is the context gathered while writing it.
- **Clear between phases**, when the next one touches different code.
- **Definitely clear before Phase D.** C left a lot of classifier output and
  actor bags in context that D — a search box and a region list — didn't
  need. Done; D was planned and built in its own session.

---

## Deployment (excluded from the plan above)

Plan phases 1–3 landed (`9b082c2`, `1e18206`, `b8eab47`): `backend/Dockerfile`,
`frontend/vercel.json`, the DB-URL scheme validator, `PRODUCTION` /
`ADMIN_TOKEN` fail-fast, per-source failure isolation, the `sweep_dropped`
guard, `ingest_runs`, and the real `/api/health`.

**Done 2026-09-03. The site is live: https://conflict-coordinate.vercel.app**,
backed by `https://api-production-6e126.up.railway.app`.

Railway project `conflict-coordinate` runs three services — `postgres`
(`postgis/postgis:16-3.4`, 5 GB volume), `api` (repo `backend/`, Dockerfile,
migrations on deploy) and `ingest` (same image, `startCommand` override, cron
`0 6 * * 2`). The database was seeded by `pg_dump`/`pg_restore` from local:
all 15 tables match row-for-row, `alembic_version` at `0014`, 563 MB restored.
`/api/health` reports `ok` with **293 dots**, the same as local.

The first production ingest was exercised through the **real cron**, not the
API route — schedule moved a few minutes ahead, watched fire, then restored:
`ingest_runs` id 10, `ok=true`, 8m31s, with ACLED OAuth, UCDP, GDELT and
ReliefWeb all reaching the network from Railway.

Four things the runbook had wrong, all corrected in `DEPLOY.md` (`a7b66d0`):
every PostGIS marketplace template is unusable (Railway's own is PG16 on an
unpinned PostGIS; both PG17 ones declare **no volume**, so the database is
wiped on redeploy); attaching a volume does not migrate the ephemeral data
already written and Railway reports its usage as `0.0 GB` regardless;
Railpack claims the build unless `backend/railway.json` pins the Dockerfile;
and a domain generated before the first successful deploy is permanently
dead — healthy service, correct `targetPort`, and a 404 from the edge that
never forwards a request.

The interim B6 crontab and its leftover 18:26 probe job were removed once the
Railway cron was proven (backup: `~/.conflict-deploy/crontab.backup`).

**Still open, both needing something a sandbox can't do:**

- **An uptime monitor on `/api/health`** — needs a signup. It distinguishes
  `ok`, `degraded` (last run failed, earlier success stands) and `stale` (no
  success within `STATUS_STALE_DAYS`), so it catches a stall that still
  returns HTTP 200. On a weekly cadence a broken pipeline is otherwise
  invisible for a week.
- **The throttle-key check** (below) — needs a second network.

Railway services have **no GitHub deploy trigger**, so pushes to `main`
rebuild the Vercel frontend but not the API or ingest — deploy those with
`serviceInstanceDeployV2`. Adding one is **blocked on connecting GitHub to
Railway**: `deploymentTriggerCreate` returns *"no one in the project has
access to it"* and `githubRepos` returns *Not Authorized*, because the Railway
GitHub App is not installed. The builds work regardless only because the repo
is public and Railway can clone it anonymously. Install the app from the
Railway dashboard (service → Settings → Source), then re-run
`deploymentTriggerCreate` for both `api` and `ingest`.

~~Two gaps the deploy plan called for and didn't get.~~ **Both closed
2026-09-03**, and both since confirmed on the deployed stack:

- ~~**No rate limiting.**~~ `app/rate_limit.py` + `SlowAPIMiddleware`, applied
  as a global default rather than per-endpoint so a new router can't ship
  unthrottled by omission. 120 req/min per client IP, keyed off the **last**
  `X-Forwarded-For` hop — the one a proxy appends and a caller therefore
  can't spoof. *Verified* against the running API: 130 requests from one IP
  → 120×200 + 10×429; a second IP unaffected; rotating the leading forwarded
  hop still 429s; the 429 carries `Retry-After` and CORS headers, so a browser
  sees a real 429 rather than an opaque network error. Admin routes are
  covered too — 120 bad-token attempts, then 429. Five unit tests pin the key
  function (`tests/test_rate_limit.py`).
- ~~**Nothing runs migrations on deploy.**~~ The API role's CMD is now
  `alembic upgrade head && uvicorn …`. *Verified* by building the image and
  running it against the local DB: migrations run, then uvicorn serves; and
  pointed at a database that doesn't exist, the container exits **1** with
  uvicorn never starting, rather than serving against a schema the code no
  longer matches. The ingest role overrides the CMD, so migrations run from
  exactly one place.

Migrations-on-deploy is now confirmed in production: the API's deploy log
shows `alembic upgrade head` running ahead of uvicorn on every release.

**The one assumption still unchecked:** the client-IP derivation assumes a
single proxy in front of the app. With two, every visitor shares one bucket
and the site throttles itself under normal traffic. The deployed API does
return `x-ratelimit-limit: 120` and a decrementing `x-ratelimit-remaining`,
but one machine cannot tell a per-client bucket from a shared one — that
needs a second network (a phone hotspot). `DEPLOY.md` §6 has the comparison
and the fix (`hops[-2]`).

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

# dots, how many carry a conflict name, and what kind of violence they are
curl -s localhost:8000/api/globe | python3 -c "
import json,sys,collections; d=json.load(sys.stdin)
print(len(d), 'dots,', sum(1 for x in d if x.get('conflict')), 'named')
print(collections.Counter(x['violence_class'] for x in d))"

# one region's label and the evidence behind it (C7)
curl -s localhost:8000/api/crises/brazil-rio-de-janeiro | python3 -c "
import json,sys; d=json.load(sys.stdin)
print(d['violence_class'], '|', d['violence_class_basis'])"

# the three four-week numbers must all agree (A3)
curl -s localhost:8000/api/crises/ukraine-donetsk | python3 -c "
import json,sys; d=json.load(sys.stdin)
print(d['violence_4w_events'], sum(a['events'] for a in d['activity']), d['stats']['recent_4w_events'])"

cd ../backend && uv run pytest -q          # 11 tests: routing guard + classifier
crontab -l                                  # the weekly ingest

docker exec conflict_db psql -U conflict -d conflict \
  -c "select id, ok, trigger, finished_at from ingest_runs order by id;" \
  -c "select max(week_start) from crisis_intensity_weekly;" \
  -c "select count(*) filter (where conflict_id is not null), count(*) from crisis_events;"

# must return 0 — no dot standing on a window with no qualifying violence (C0)
docker exec conflict_db psql -U conflict -d conflict -c "
with latest as (select max(week_start) w from crisis_intensity_weekly)
select count(*) from crises c
where (c.violence_4w_events>=5 or c.violence_4w_fatalities>=5)
  and not exists (select 1 from crisis_intensity_weekly w, latest
                  where w.crisis_id=c.id
                    and w.week_start > latest.w - interval '4 weeks'
                    and w.event_type in ('Battles','Violence against civilians',
                                         'Explosions/Remote violence','Riots'));"

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
