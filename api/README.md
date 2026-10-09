# holibase-api

Public read API for Holibase as a Cloudflare Worker in front of Supabase.
Reachable at `https://api.holibase.org`.

## Endpoints

| Method | Path | Notes |
|---|---|---|
| GET | `/v1/countries` | countries + subdivisions |
| GET | `/v1/public-holidays/{CC}/{YYYY}?subdivision=&lang=` | one calendar year |
| GET | `/v1/public-holidays/{CC}?from=&to=&subdivision=&lang=` | free range, max 3 years |
| GET | `/v1/school-holidays/{CC}?subdivision=&from=&to=` | default: today + 12 months |
| GET | `/v1/authorities?country=&q=&subdivision=&limit=` | search school authorities (US districts, English councils, NL regions, FR zones, BE communities, Swiss variants) |
| GET | `/v1/authorities/{id}` | one authority with its calendars |
| GET | `/v1/school-holidays/{CC}?authority={id}&from=&to=&lang=` | school holidays of an authority, plus `calendars` (first/last day, status, source) |
| GET | `/v1/school-holidays/{CC}?…&include=pending` | also return calendars that are not yet verified |
| GET | `/data/<path>.json` | static files from R2 (layout of the repo's `data/`) |
| GET | `/v1/health` | liveness |

Codes are case-insensitive (`de`, `de-by`, `EN`); the cache key is normalised.
Errors: `{"error":{"code","message"}}` with status 400/404/405/429/502/503.

## Behaviour

- **Edge cache** (Cache API): public holidays 24 h, school holidays 6 h, reference data 24 h (`TTL_*` vars).
  Cache hits never reach Supabase and do not count against the rate limit.
- **ETag / 304** on every 200 response.
- **Rate limit**: 120 requests/min per IP, cache misses only.
- **CORS** open (`*`), GET/HEAD/OPTIONS only.
- The Supabase key stays a Worker secret and is never exposed.

## Setup (once)

```bash
npm install
npx wrangler login
# 1. set SUPABASE_URL in wrangler.toml to the Holibase project URL
# 2. key as secret (publishable/anon key is enough, RLS keeps the data read-only):
npx wrangler secret put SUPABASE_KEY
# 3. deploy; creates api.holibase.org including DNS record and certificate:
npx wrangler deploy
# 4. optional: static files into R2
bash scripts/upload-data.sh ../data
```

Prerequisite for step 3: the zone `holibase.org` is active in the same Cloudflare account.
Do not create a DNS record for `api` by hand.

## Local

```bash
echo 'SUPABASE_KEY=...' > .dev.vars
npx wrangler dev
curl "http://localhost:8787/v1/public-holidays/DE/2026?subdivision=DE-BY"
```
