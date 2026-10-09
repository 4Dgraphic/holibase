"""
Import the US school district directory from NCES (public domain) into education_authorities.

    DATABASE_URL=postgresql://... python scripts/import_nces.py [--dry-run] [--fixture DIR]

Sources (both official NCES ArcGIS services, no API key):
  A  EDGE geocode file of all public LEAs (newest school year is found automatically)
     https://nces.ed.gov/opengis/rest/services/K12_School_Locations/EDGE_GEOCODE_PUBLICLEA_<YYYY>/MapServer/0
     -> every agency: id, name, city, state, county, coordinates
  B  School District Characteristics - Current (CCD administrative data on district boundaries)
     -> agency type, status, students, grade span

What it does
  * One row per NCES LEAID (unique index on external_ids->>'nces_leaid').
  * Authorities that already exist (editorial research, e.g. "Gwinnett County Public Schools") are matched by
    state + name and keep their id, name and calendars; they only gain the real nces_leaid and NCES facts.
    A research claim (nces_leaid_claimed) is only used to break ties or as a flagged last resort.
    data/nces/overrides.json pins a match by hand: {"<authority uuid>": "<leaid>" | null}.
  * New agencies get a deterministic id (uuid5 of the LEAID), source 'nces-ccd'.
  * Agencies that disappear from NCES are set inactive, never deleted (calendars may point to them).
  * Safety: aborts when NCES returns fewer than 15,000 agencies or when more than 5 % would be deactivated.
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
import uuid
from collections import Counter, defaultdict

GEOCODE_FOLDER = "https://nces.ed.gov/opengis/rest/services/K12_School_Locations"
CHARACTERISTICS = ("https://services1.arcgis.com/Ua5sjt3LWTPigjyD/arcgis/rest/services/"
                   "School_District_Characteristics_Current/FeatureServer/0")
NCES_NAMESPACE = uuid.UUID("2b8f6f0e-5a7c-4d1e-9a51-8f3e0c4b7d22")
SOURCE_ID = "nces-ccd"
MIN_ROWS = 15000
MAX_DEACTIVATE_RATIO = 0.05

# CCD LEA_TYPE codes
LEA_TYPES = {
    "1": "Regular local school district",
    "2": "Local school district that is a component of a supervisory union",
    "3": "Supervisory union",
    "4": "Regional education service agency",
    "5": "State agency",
    "6": "Federal agency",
    "7": "Charter agency",
    "8": "Other education agency",
    "9": "Specialized public school district",
}
DISTRICT_TYPES = {"1", "2"}


# ------------------------------------------------------------------ fetching

def http_json(url: str, params: dict | None = None, tries: int = 5) -> dict:
    if params:
        url += "?" + urllib.parse.urlencode(params)
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "holibase-import/1.0 (+https://holibase.org)"})
            with urllib.request.urlopen(req, timeout=90) as r:
                data = json.load(r)
            if "error" in data:
                raise RuntimeError(f"ArcGIS error: {data['error']}")
            return data
        except Exception as e:  # network hiccups are common on these services
            if attempt == tries - 1:
                raise
            print(f"  retry {attempt + 1} after {e}", flush=True)
            time.sleep(3 * (attempt + 1))
    raise AssertionError


def latest_geocode_layer() -> tuple[str, str]:
    services = http_json(GEOCODE_FOLDER, {"f": "json"}).get("services", [])
    years = sorted(m.group(1) for s in services if (m := re.search(r"EDGE_GEOCODE_PUBLICLEA_(\d{4})$", s["name"])))
    if not years:
        raise RuntimeError("No EDGE_GEOCODE_PUBLICLEA service found")
    y = years[-1]
    return f"{GEOCODE_FOLDER}/EDGE_GEOCODE_PUBLICLEA_{y}/MapServer/0", f"20{y[:2]}-{y[2:]}"


def fetch_layer(layer: str, fields: list[str], chunk: int = 1000) -> list[dict]:
    """All records of an ArcGIS layer, paged by OBJECTID ranges (works on MapServer and FeatureServer)."""
    ids = http_json(f"{layer}/query", {"where": "1=1", "returnIdsOnly": "true", "f": "json"})["objectIds"] or []
    ids.sort()
    out: list[dict] = []
    for i in range(0, len(ids), chunk):
        lo, hi = ids[i], ids[min(i + chunk, len(ids)) - 1]
        data = http_json(f"{layer}/query", {
            "where": f"OBJECTID>={lo} AND OBJECTID<={hi}",
            "outFields": ",".join(fields),
            "returnGeometry": "false",
            "f": "json",
        })
        out += [f["attributes"] for f in data.get("features", [])]
        print(f"  {len(out):>6} / {len(ids)}", flush=True)
    return out


# ------------------------------------------------------------------ cleaning

def clean(v) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


SMALL = {"of", "and", "the", "for", "in", "at", "de", "la"}
KEEP_UPPER = {"ISD", "CISD", "USD", "CUSD", "ESD", "SD", "UFSD", "CSD", "BOCES", "RSD", "PSD", "II", "III", "IV",
              "VI", "VII", "VIII", "IX", "XI", "XII", "DC", "CSA", "ROE", "ESC", "IU", "ESU", "SAU", "RSU", "MSAD"}


def nice_case(s: str | None) -> str | None:
    """'FORT LAUDERDALE' -> 'Fort Lauderdale'; mixed-case input stays as it is."""
    if not s or not s.isupper():
        return s
    words = []
    for i, w in enumerate(s.split()):
        core = re.sub(r"[^A-Z0-9]", "", w)
        if core in KEEP_UPPER or re.fullmatch(r"[A-Z]?-?\d+[A-Z]?", core) or re.fullmatch(r"[A-Z]+-\d+", w):
            words.append(w)
        elif i and w.lower() in SMALL:
            words.append(w.lower())
        else:
            words.append("-".join(p[:1] + p[1:].lower() for p in w.split("-")))
    out = " ".join(words)
    return re.sub(r"\b(Mc)([a-z])", lambda m: m.group(1) + m.group(2).upper(), out)


def number(v) -> int | None:
    try:
        n = int(float(v))
    except (TypeError, ValueError):
        return None
    return n if n >= 0 else None  # CCD uses negative codes for missing / not applicable


def build_directory(geo: list[dict], chars: list[dict], geo_year: str) -> dict[str, dict]:
    by_id: dict[str, dict] = {}
    for r in geo:
        leaid = clean(r.get("LEAID"))
        if not leaid:
            continue
        by_id[leaid] = {
            "leaid": leaid, "name": clean(r.get("NAME")), "city": clean(r.get("CITY")), "state": clean(r.get("STATE")),
            "county": clean(r.get("NMCNTY")), "lat": r.get("LAT"), "lon": r.get("LON"), "locale": clean(r.get("LOCALE")),
            "year": geo_year, "lea_type": None, "status": None, "students": None, "grades": None, "phone": None,
        }
    for r in chars:
        leaid = clean(r.get("LEAID"))
        if not leaid:
            continue
        d = by_id.setdefault(leaid, {"leaid": leaid, "year": clean(r.get("SURVYEAR")), "locale": None})
        d["name"] = clean(r.get("LEA_NAME")) or d.get("name")
        d["city"] = d.get("city") or clean(r.get("LCITY"))
        d["state"] = d.get("state") or clean(r.get("LSTATE"))
        d["county"] = d.get("county") or clean(r.get("CONAME"))
        if d.get("lat") is None:
            d["lat"], d["lon"] = r.get("Lat"), r.get("Long")
        d["lea_type"] = clean(r.get("LEA_TYPE"))
        d["status"] = clean(r.get("SY_STATUS_TEXT"))
        d["students"] = number(r.get("MEMBER"))
        lo, hi = clean(r.get("GSLO")), clean(r.get("GSHI"))
        d["grades"] = f"{lo}-{hi}" if lo and hi else None
        d["phone"] = clean(r.get("PHONE"))
    for d in by_id.values():
        d["name"] = nice_case(d.get("name")) or d["leaid"]
        d["city"] = nice_case(d.get("city"))
        d["county"] = nice_case(d.get("county"))
        if d.get("lea_type") in DISTRICT_TYPES:
            d["kind"] = "school_district"
        else:
            d["kind"] = "other"
    return by_id


# ------------------------------------------------------------------ matching

STOP = {"public", "schools", "school", "district", "districts", "independent", "isd", "unified", "usd", "the", "of",
        "department", "education", "system", "sd", "dept", "ps", "pss", "consolidated", "community", "board", "and"}
ALIASES = {"nyc": "new york city", "jeffco": "jefferson county", "metro": "metropolitan", "dc": "district columbia",
           "miami-dade": "dade", "miami dade": "dade"}


def tokens(name: str, drop_place: bool = False) -> tuple[str, ...]:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = s.replace("&", " and ").replace("'", "")
    for a, b in ALIASES.items():
        s = re.sub(rf"\b{re.escape(a)}\b", b, s)
    words = [w for w in re.split(r"[^a-z0-9]+", s) if w and w not in STOP]
    if drop_place:
        words = [w for w in words if w not in {"county", "city", "parish", "borough"}]
    return tuple(words)


def match(existing: dict, directory: dict[str, dict], by_state: dict[str, list[dict]], taken: set[str]) -> tuple[str | None, str]:
    """Returns (leaid, how) for an existing authority, or (None, reason)."""
    state = (existing["subdivision_code"] or "")[3:]
    cands = [d for d in by_state.get(state, []) if d["leaid"] not in taken]
    claimed = (existing["external_ids"] or {}).get("nces_leaid_claimed")
    own = tokens(existing["name"])

    def pick(found: list[dict], how: str):
        if len(found) == 1:
            return found[0]["leaid"], how
        if len(found) > 1:
            if claimed and any(d["leaid"] == claimed for d in found):
                return claimed, how + "+claim"
            districts = [d for d in found if d["kind"] == "school_district"]
            if len(districts) == 1:
                return districts[0]["leaid"], how + "+type"
            return None, f"ambiguous: {', '.join(d['leaid'] for d in found[:4])}"
        return None, ""

    for how, test in (
        ("name", lambda d: tokens(d["name"]) == own),
        ("name-without-county", lambda d: tokens(d["name"], True) == tokens(existing["name"], True) and tokens(d["name"], True)),
        ("name-subset", lambda d: len(tokens(d["name"])) >= 2 and set(tokens(d["name"])) <= set(own)),
    ):
        leaid, why = pick([d for d in cands if test(d)], how)
        if leaid or why:
            return leaid, why
    # Closest name with high similarity
    scored = sorted(((difflib.SequenceMatcher(None, " ".join(own), " ".join(tokens(d["name"]))).ratio(), d) for d in cands),
                    key=lambda x: -x[0])
    if scored and scored[0][0] >= 0.9 and (len(scored) == 1 or scored[1][0] < scored[0][0] - 0.05):
        return scored[0][1]["leaid"], f"similar {scored[0][0]:.2f}"
    if claimed and claimed in directory and claimed not in taken and (directory[claimed]["state"] or "") == state:
        return claimed, "CHECK: research claim, names differ"
    return None, "no match"


# ------------------------------------------------------------------ main

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--fixture", help="directory with geocode.json / characteristics.json instead of downloading")
    args = ap.parse_args()
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("DATABASE_URL is not set")
        return 2
    import psycopg
    from psycopg.types.json import Jsonb

    if args.fixture:
        geo = json.load(open(os.path.join(args.fixture, "geocode.json")))
        chars = json.load(open(os.path.join(args.fixture, "characteristics.json")))
        geo_year, min_rows = "fixture", 1
    else:
        layer, geo_year = latest_geocode_layer()
        print(f"Geocode layer {layer} ({geo_year})", flush=True)
        geo = fetch_layer(layer, ["OBJECTID", "LEAID", "NAME", "CITY", "STATE", "NMCNTY", "LAT", "LON", "LOCALE"])
        print("Characteristics layer", flush=True)
        chars = fetch_layer(CHARACTERISTICS, ["OBJECTID", "LEAID", "LEA_NAME", "LCITY", "LSTATE", "CONAME", "LEA_TYPE",
                                              "SY_STATUS_TEXT", "MEMBER", "GSLO", "GSHI", "PHONE", "SURVYEAR", "Lat", "Long"])
        min_rows = MIN_ROWS
    directory = build_directory(geo, chars, geo_year)
    if len(directory) < min_rows:
        print(f"Only {len(directory)} agencies from NCES (expected at least {min_rows}). Aborting.")
        return 1

    overrides_path = os.path.join(os.path.dirname(__file__), "..", "data", "nces", "overrides.json")
    overrides = json.load(open(overrides_path)) if os.path.exists(overrides_path) else {}
    overrides = {k: v for k, v in overrides.items() if not k.startswith("_")}

    stats = Counter()
    report: list[str] = []
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("select code from public.subdivisions where country_code = 'US'")
        subdivisions = {r[0] for r in cur.fetchall()}
        cur.execute("""select id::text, name, subdivision_code, external_ids, source_id
                         from public.education_authorities where country_code = 'US'""")
        existing = [dict(zip(("id", "name", "subdivision_code", "external_ids", "source_id"), r)) for r in cur.fetchall()]

        # 1. Which existing row owns which LEAID
        owner: dict[str, str] = {}  # leaid -> authority id
        for e in existing:
            leaid = (e["external_ids"] or {}).get("nces_leaid")
            if leaid:
                owner[leaid] = e["id"]
        by_state: dict[str, list[dict]] = defaultdict(list)
        for d in directory.values():
            by_state[d["state"] or ""].append(d)
        for e in existing:
            if (e["external_ids"] or {}).get("nces_leaid"):
                continue
            if e["id"] in overrides:
                leaid, how = overrides[e["id"]], "override"
                if leaid and leaid not in directory:
                    leaid, how = None, f"override {overrides[e['id']]} not in NCES"
            else:
                leaid, how = match(e, directory, by_state, set(owner))
            claimed = (e["external_ids"] or {}).get("nces_leaid_claimed")
            if leaid and leaid not in owner:
                owner[leaid] = e["id"]
                d = directory[leaid]
                note = f" (research claimed {claimed})" if claimed and claimed != leaid else ""
                report.append(f"| {e['name']} | {e['subdivision_code']} | {leaid} {d['name']} | {how}{note} |")
                stats["matched_existing"] += 1
                if claimed and claimed != leaid:
                    stats["claims_corrected"] += 1
            else:
                report.append(f"| {e['name']} | {e['subdivision_code']} | – | {how or 'not found'} |")
                stats["unmatched_existing"] += 1

        # 2. Rows to write
        rows = []
        for leaid, d in directory.items():
            sub = f"US-{d['state']}" if d.get("state") and f"US-{d['state']}" in subdivisions else None
            if sub is None:
                stats["without_subdivision"] += 1
            ext = {k: v for k, v in {
                "nces_leaid": leaid,
                "nces_name": d["name"],
                "nces_lea_type": d.get("lea_type"),
                "nces_lea_type_text": LEA_TYPES.get(d.get("lea_type") or ""),
                "nces_status": d.get("status"),
                "nces_school_year": d.get("year"),
                "county": d.get("county"),
                "grades": d.get("grades"),
                "phone": d.get("phone"),
                "locale": d.get("locale"),
                "lat": round(d["lat"], 6) if isinstance(d.get("lat"), (int, float)) else None,
                "lon": round(d["lon"], 6) if isinstance(d.get("lon"), (int, float)) else None,
            }.items() if v is not None}
            rows.append((owner.get(leaid) or str(uuid.uuid5(NCES_NAMESPACE, leaid)), sub, d["kind"], d["name"],
                         Jsonb(ext), d.get("city"), d.get("students"), leaid in owner))
            stats["kind_" + d["kind"]] += 1

        # 3. Deactivation guard
        cur.execute("""select count(*) from public.education_authorities
                        where source_id = %s and is_active and not (external_ids->>'nces_leaid' = any(%s))""",
                    (SOURCE_ID, list(directory)))
        to_deactivate = cur.fetchone()[0]
        cur.execute("select count(*) from public.education_authorities where source_id = %s and is_active", (SOURCE_ID,))
        active = cur.fetchone()[0]
        if active and to_deactivate / active > MAX_DEACTIVATE_RATIO:
            print(f"Would deactivate {to_deactivate} of {active} NCES agencies (> {MAX_DEACTIVATE_RATIO:.0%}). Aborting.")
            return 1

        # 4. Write. Existing (editorial) rows keep id, name, kind and source; they gain NCES facts.
        cur.execute("""create temp table nces_in (id uuid, subdivision_code text, kind text, name text, ext jsonb,
                       city text, students int, is_existing boolean) on commit drop""")
        with cur.copy("copy nces_in from stdin") as cp:
            for r in rows:
                cp.write_row(r)
        cur.execute("""
            with upd as (
              update public.education_authorities a
                 set external_ids = (a.external_ids - 'nces_leaid_claimed') || n.ext,
                     city = coalesce(a.city, n.city),
                     student_count = n.students,
                     is_active = true,
                     updated_at = now()
                from nces_in n
               where n.is_existing and a.id = n.id
                 and (a.external_ids is distinct from (a.external_ids - 'nces_leaid_claimed') || n.ext
                      or a.student_count is distinct from n.students or not a.is_active)
              returning 1)
            select count(*) from upd""")
        stats["existing_updated"] = cur.fetchone()[0]
        cur.execute("""
            with ins as (
              insert into public.education_authorities
                     (id, country_code, subdivision_code, kind, name, external_ids, city, student_count, is_active, source_id)
              select id, 'US', subdivision_code, kind, name, ext, city, students, true, %s
                from nces_in where not is_existing
              on conflict (id) do update set
                     subdivision_code = excluded.subdivision_code, kind = excluded.kind, name = excluded.name,
                     external_ids = excluded.external_ids, city = excluded.city, student_count = excluded.student_count,
                     is_active = true, updated_at = now()
               where (education_authorities.subdivision_code, education_authorities.kind, education_authorities.name,
                      education_authorities.external_ids, education_authorities.city, education_authorities.student_count,
                      education_authorities.is_active)
                     is distinct from
                     (excluded.subdivision_code, excluded.kind, excluded.name, excluded.external_ids, excluded.city,
                      excluded.student_count, true)
              returning (xmax = 0) as inserted)
            select count(*) filter (where inserted), count(*) filter (where not inserted) from ins""", (SOURCE_ID,))
        stats["nces_inserted"], stats["nces_updated"] = cur.fetchone()
        cur.execute("""update public.education_authorities set is_active = false, updated_at = now()
                        where source_id = %s and is_active and not (external_ids->>'nces_leaid' = any(%s))""",
                    (SOURCE_ID, list(directory)))
        stats["nces_deactivated"] = cur.rowcount
        stats["agencies_from_nces"] = len(directory)
        stats["with_characteristics"] = sum(1 for d in directory.values() if d.get("lea_type"))

        summary = (f"## NCES district import {'(dry run)' if args.dry_run else ''}\n\nSchool year {geo_year}\n\n"
                   + "\n".join(f"- {k}: {v}" for k, v in sorted(stats.items()))
                   + "\n\n### Existing authorities\n\n| Authority | State | NCES | Match |\n|---|---|---|---|\n"
                   + "\n".join(sorted(report)) + "\n")
        print(summary)
        if os.environ.get("GITHUB_STEP_SUMMARY"):
            with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
                f.write(summary)
        if args.dry_run:
            conn.rollback()
            print("Dry run: rolled back.")
        else:
            conn.commit()
            print("Committed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
