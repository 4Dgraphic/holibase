# Holibase

Open database and API for **public holidays and school holidays worldwide**, with a community
ingest for school calendars where no central source exists (above all US school districts).

- API: `https://api.holibase.org` (Cloudflare Worker in `api/`, see `api/README.md`)
- Database: Supabase project "Holibase" (Postgres 17)

## What is in the data

| Dataset | Coverage | Source |
|---|---|---|
| Public holidays | 250 countries, all python-holidays subdivisions, window 2020 – current year + 10, names in every language the source offers | python-holidays (MIT), synced weekly |
| School holidays | Germany (16 states + Augsburg), Australia (8 states/territories), school days for BG, EG, IL, LA, TH, YE | python-holidays (MIT), synced weekly |
| School districts | all ~19,000 US public school agencies with NCES id, city, county, coordinates, type, students | NCES EDGE + CCD (public domain), monthly |
| Calendar feeds | iCalendar (`.ics`) for every holiday query, subscribable via webcal | API |
| Editorial / community calendars | in progress (US districts, DACH, Benelux, FR, UK) | own research, submissions |

## Repository layout

```
.github/workflows/sync-holidays.yml   weekly library sync (GitHub Actions)
api/                                  public read API (Cloudflare Worker, Wrangler project)
scripts/build.py                      builds rows from python-holidays (no database needed)
scripts/sync.py                       syncs the build into the database (insert / update / delete)
scripts/fingerprint.py                per-country fingerprints, to compare a build with the database
scripts/import_editorial.py           imports reviewed school calendars from data/editorial/
scripts/import_nces.py                imports the US school district directory from NCES
scripts/import_official.py            imports school holidays from official open data (NL, FR)
scripts/research_to_editorial.py      validates deep-research results and turns them into editorial calendars
scripts/auto_research.py              finds missing school calendars in official documents (language model)
scripts/data_report.py                monthly data report (GitHub issue)
supabase/migrations/                  database schema
supabase/seed.sql                     data sources (run once after the schema)
web/                                  website holibase.org (static, Cloudflare Worker assets)
```

## Library sync

`scripts/sync.py` keeps the python-holidays data current. It runs every Monday via GitHub Actions
and can be started by hand (Actions → "Sync library holidays" → Run workflow).

- **Window:** 2020 to the current year + 10. It moves forward by itself every January.
  Rows before the window are never touched, so history stays.
- **Recompute, not append:** every run rebuilds the whole window with the newest library release,
  so corrections reach past and future years too: law changes, new or abolished holidays,
  confirmed dates for moon-sighting holidays (`is_estimated`).
- **Only library rows:** rows with `source_id = 'python-holidays'` and school calendars with
  `origin = 'library'`. Editorial and community data is never modified.
- **Early exit:** nothing happens when the database already has the current library version
  and the full window.
- **Safety guard:** the run aborts (and rolls back) when it would delete more than 5 % of the rows
  in the window. That protects against a broken library release.
- **Report:** inserted / changed / deleted per table and per country, in the job summary.

### Setup (once)

1. Supabase → **Connect** → *Session pooler* → copy the URI
   (`postgresql://postgres.<ref>:<password>@aws-…-eu-west-1.pooler.supabase.com:5432/postgres`).
   Use the pooler: GitHub runners have no IPv6, the direct host does not work there.
2. GitHub → repository **Settings → Secrets and variables → Actions → New repository secret**:
   name `DATABASE_URL`, value = the URI with your database password.
3. Actions → "Sync library holidays" → **Run workflow** with *Dry run* checked. Read the summary.
4. Run it again without *Dry run*. From then on the weekly schedule takes over.

### Local

```bash
python3 -m venv .venv && .venv/bin/pip install -r scripts/requirements.txt
DATABASE_URL=postgresql://... .venv/bin/python scripts/sync.py --dry-run
.venv/bin/python scripts/sync.py --countries DE,AT --force      # only some countries
```

## Data model in five rules

1. **Region or nation, never both.** `subdivision_code IS NULL` holds the national set.
   A subdivision holds its *complete* set, nationwide days included (`scope = 'national'`).
2. **`is_observed` = shifted date, still a real day off** (substitute days, moved holidays).
3. **`is_estimated`** marks dates that depend on moon sighting and can still move.
4. **Categories matter.** Default is `public`; others: `bank`, `government`, `optional`,
   `workday`, religious ones such as `catholic`.
5. **Every row knows its source and licence** (`sources`).

Names: `names` holds one entry per language (`de`, `en-US`, …). Translations are looked up by
message id in python-holidays, so they stay attached to the right holiday when several share a
date. The API falls back from the requested language to its base language, then English, then
the local name.

Subdivision codes follow ISO 3166-2. Named areas without an ISO code become slugs
(`DE-AUGSBURG`, `BR-SAO-PAULO-CAPITAL`, `CH-STADT-ZURICH`).

## Licences

Everything is free to use, also commercially. The only condition is credit.

| What | Licence | Credit |
|---|---|---|
| Code (this repository) | MIT (`LICENSE`) | – |
| Holibase's own data: editorial and community school calendars, authority directory, the compiled database | CC BY 4.0 (`LICENSE-DATA`) | "Holibase (holibase.org), CC BY 4.0" |
| Public and school holidays from python-holidays | MIT | "© python-holidays contributors" |
| School holidays from OpenHolidays API (calendars with `source_id = 'openholidays'`) | ODbL 1.0, share-alike | "School holidays from OpenHolidays API (openholidaysapi.org), ODbL 1.0" |
| US school district directory (NCES CCD / EDGE) | public domain (U.S. federal government) | "Source: U.S. Department of Education, NCES" (courtesy) |

The API returns the credit line in every response (`attribution`, `license`) and in every iCalendar feed.

OpenHolidays data is share-alike (ODbL). Holibase keeps it as its own, identifiable layer: every such
calendar carries `source_id: "openholidays"` and `license: "ODbL-1.0"`, responses that contain one credit
OpenHolidays, and if you redistribute those calendars as a database, they stay under ODbL. An app or page
that only displays the data (a "produced work") needs the credit, not the share-alike.

## OpenHolidays import

`scripts/import_openholidays.py` reads github.com/openpotato/openholidaysapi.data every Wednesday
(`.github/workflows/import-openholidays.yml`) and adds the school calendars of every country it covers,
except France and the Netherlands (official data) and Belgium (not mapped yet). It only fills gaps: for the
same region and school year, official, editorial and community calendars and python-holidays win
(`public.calendar_rank`, `public.calendar_visible`). Partial school years (fewer than three breaks) are
left out; a country whose calendar count suddenly halves is skipped. The job summary shows how well the
data agrees with the calendars Holibase already has.

## Editorial school calendars

Reviewed calendars live in `data/editorial/*.json` (one file per research batch) and are imported by
`.github/workflows/import-editorial.yml` whenever such a file changes on `main`.

- `status: confirmed` only when the dates were cross-checked against a second source (KMK, Länder
  Ferienordnungen, oesterreich.gv.at, OpenHolidays for cross-checking only, district PDFs) or come from
  the authority's own official calendar. Everything else is `pending` and only returned by the API with
  `p_include_pending`.
- First and last day of instruction are stored on the calendar (`first_day`, `last_day`), not as periods.
- When an editorial calendar and a library calendar cover the same scope and school year, the API returns
  the editorial one.
- US districts carry the NCES id reported by the research as `external_ids.nces_leaid_claimed` until the NCES
  import sets the real `nces_leaid` (see below).

## Official school holiday sources

`scripts/import_official.py` pulls school holidays from official government open data, weekly via
`.github/workflows/import-official.yml` (a push of the importer runs a dry run with a comparison report).

| Source | Scope | Licence |
|---|---|---|
| Rijksoverheid open data | Netherlands, regions noord / midden / zuid | CC0-1.0 |
| Éducation nationale, calendrier scolaire | France, zones A / B / C, Corse, overseas departments and territories | Licence Ouverte 2.0 |

- Calendars are `origin = 'official'`. Research calendars for the same scope and school year are compared break by
  break and then marked `outdated` ("Superseded by official data"); the editorial import leaves them that way.
- If more than 20 % of the compared breaks disagree, the source is skipped and the last good data stays
  (the format probably changed). A failed download changes nothing.
- French dates mean "after classes" and "classes resume"; the free days stored are start + 1 to end − 1.
- More candidate sources (with licence status) are listed in `data/research/` and the source registry.

## US district research

`data/research/us-2026-10/` holds the next research round: the 499 largest districts without a verified
calendar, as 10 ready-to-paste prompts. Results dropped into `results/` are validated and imported on push
(see the README there).

## US school districts (NCES)

`scripts/import_nces.py` loads the US school district directory, runs monthly via
`.github/workflows/import-nces.yml` and whenever `data/nces/**` changes.

- **Sources:** NCES EDGE geocode file of all public LEAs (newest school year, found automatically) and NCES
  "School District Characteristics – Current" (CCD: type, status, students, grades). Both are U.S. government
  works in the public domain, read from NCES's ArcGIS services.
- **One row per NCES LEAID.** New agencies get a deterministic id (uuid5 of the LEAID). Real districts
  (CCD type 1 and 2) are `school_district`; charter agencies, service agencies and others are `other`, with the
  NCES type in `external_ids.nces_lea_type`.
- **Existing districts keep their id, name and calendars.** They are matched by state and name
  ("Gwinnett County Public Schools" = NCES "Gwinnett County School District"); the research claim only breaks
  ties or is used as a last resort marked *CHECK* in the run summary. `data/nces/overrides.json` pins a match by
  hand (`"<authority uuid>": "<LEAID>"`, `null` = never match).
- **Nothing is deleted.** Agencies that leave the NCES directory become `is_active = false`.
- **Safety:** aborts when NCES returns fewer than 15,000 agencies or more than 5 % would be deactivated.

## Website

`web/` is the static site at holibase.org: no framework, no build dependencies.
Google Analytics loads only after consent in the cookie banner (`web/public/assets/consent.js`). `www.` redirects to the apex domain (`web/src/worker/index.js`).
Pages live in `web/src/pages/` (front matter on top), shared header and footer in `web/src/partials/`,
CSS, JavaScript and fonts in `web/public/assets/`. Colours, type and spacing follow the Holibase design system.

```
python web/build.py                                    # writes the HTML into web/public/
python -m http.server -d web/public 8080               # then open http://localhost:8080/
http://localhost:8080/calendar/?api=http://localhost:8787   # use a local API (wrangler dev in api/)
```

Generated pages: one static page per school calendar region and district (`/school-holidays/...`) and per
country (`/public-holidays/...`), with the dates in the HTML, FAQ and structured data, plus `sitemap.xml`,
`llms.txt` and `assets/pages.json`. They are built from a snapshot of the database (`web/snapshot.py`,
read-only) by `web/generate.py`:

```
DATABASE_URL=postgresql://... python web/build.py --fetch    # snapshot + all pages
```

`.github/workflows/deploy-web.yml` builds and deploys on every push to `web/` and every morning, so the
generated pages stay current (secrets: the Cloudflare ones as for the API, plus `DATABASE_URL`).

## Monthly data report

`scripts/data_report.py` (`.github/workflows/data-report.yml`, 1st of every month) posts a GitHub issue
labelled `data-report`: market readiness per country (priority markets first), regions whose next school
year is missing, sources that disagree, unverified calendars, overdue sources and the last run of every
automatic job. Last month's issue is closed, so the open one is always current and each new one arrives
by email. Run it any time from the Actions tab.

## Automatic research

`scripts/auto_research.py` (`.github/workflows/auto-research.yml`, on the 28th of every month) fills the gaps the data
report lists: regions whose current or next school year has no confirmed calendar. For each country it
reads the official pages in `data/research/sources.json`, or searches the web for them (only URLs on the
country's official domains are used; discovered sources that deliver are saved back to the file). A
language model copies the dates out of the document; the script then checks them:

- **rejected** when implausible (outside the school year, overlapping breaks, no Christmas break, …);
- **pending** when they contradict another source, or not every date is printed in the document;
- **confirmed** when every date was found in the official document, or a second source agrees.

The result is imported and committed as `data/editorial/auto-<date>.json` (revert the commit to undo it),
and a summary is added to the open data report issue. Set the `OPENAI_API_KEY` secret (optional variable
`OPENAI_MODEL`, default `gpt-5-mini`) or `ANTHROPIC_API_KEY` (`ANTHROPIC_MODEL`). Each run reads at most
80 documents (a share per country) and does at most 25 web searches; `HORIZON` in the script (or `horizon` per
country in sources.json) sets how many school years ahead a country is kept filled (2, or 4 for DE, AT, CH, NL, BE, LU); run it by hand from the Actions tab for one country, with a
dry run first if you like.
