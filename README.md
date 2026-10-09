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
supabase/migrations/                  database schema
supabase/seed.sql                     data sources (run once after the schema)
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
| US school district directory (NCES CCD / EDGE) | public domain (U.S. federal government) | "Source: U.S. Department of Education, NCES" (courtesy) |

The API returns the credit line in every response (`attribution`, `license`) and in every iCalendar feed.

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
