"""
Import school holidays from official, machine-readable government sources.

    DATABASE_URL=postgresql://... python scripts/import_official.py [--dry-run] [--only nl,fr] [--fixture DIR] [--force]

Sources (open licences that allow reuse with credit):
  nl  Rijksoverheid open data, school holidays per region (CC0-1.0)
      https://opendata.rijksoverheid.nl/v1/infotypes/schoolholidays?output=json
  fr  Ministère de l'Éducation nationale, calendrier scolaire (Licence Ouverte / Etalab 2.0)
      https://data.education.gouv.fr/explore/dataset/fr-en-calendrier-scolaire/

How it works
  * Every adapter downloads the full dataset and turns it into calendars (one per scope and school year).
    Calendars get origin 'official', a deterministic id and their periods are replaced on each run.
  * Editorial calendars for the same scope and school year are compared period by period, then marked
    'outdated' (superseded). If more than 20 % of the compared breaks disagree, the run aborts: the source
    format probably changed, and the last good data stays (override with --force after checking).
  * Nothing is written when a download fails or returns no calendars.
"""
from __future__ import annotations

import argparse
import datetime as dt
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
from zoneinfo import ZoneInfo

OFFICIAL_NS = uuid.UUID("9d4c1a7e-3b2f-4e8a-b6d5-0f7e2c9a1b34")
MAX_MISMATCH_RATIO = 0.20
UA = "holibase-import/1.0 (+https://holibase.org)"

SOURCES = {
    "rijksoverheid-nl": dict(
        name="Rijksoverheid open data: schoolvakanties", url="https://www.rijksoverheid.nl/opendata/schoolvakanties",
        license="CC0-1.0", attribution="Bron: Rijksoverheid (CC0)"),
    "education-gouv-fr": dict(
        name="Ministère de l'Éducation nationale: calendrier scolaire",
        url="https://data.education.gouv.fr/explore/dataset/fr-en-calendrier-scolaire/",
        license="etalab-2.0", attribution="Source : Ministère de l'Éducation nationale, Licence Ouverte 2.0"),
}


def http_get(url: str, tries: int = 4) -> bytes:
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read()
        except Exception as e:
            if attempt == tries - 1:
                raise
            print(f"  retry {attempt + 1} after {e}", flush=True)
            time.sleep(4 * (attempt + 1))
    raise AssertionError


def school_year(raw: str) -> str:
    raw = raw.strip()
    m = re.fullmatch(r"(\d{4})\s*[-/]\s*(\d{2,4})", raw)
    if m:
        return f"{m.group(1)}-{m.group(2)[-2:]}"
    if re.fullmatch(r"\d{4}", raw):
        return raw
    raise ValueError(f"unknown school year {raw!r}")


def local_date(ts: str, tz: str) -> dt.date:
    """'2026-10-09T22:00:00.000Z' -> local calendar date in tz. Plain dates pass through."""
    ts = ts.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", ts):
        return dt.date.fromisoformat(ts)
    d = dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if d.tzinfo is None:
        return d.date()
    return d.astimezone(ZoneInfo(tz)).date()


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


# ------------------------------------------------------------------ Netherlands

NL_URL = "https://opendata.rijksoverheid.nl/v1/infotypes/schoolholidays?output=json"
NL_REGIONS = {"noord": "Regio Noord", "midden": "Regio Midden", "zuid": "Regio Zuid"}


def _walk(obj):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v)


def adapter_nl(raw: bytes) -> list[dict]:
    data = json.loads(raw)
    cals: dict[tuple[str, str], dict] = {}
    seen_years = set()
    for node in _walk(data):
        if "vacations" not in node or "schoolyear" not in node:
            continue
        year = school_year(str(node["schoolyear"]))
        if year in seen_years:
            continue  # the same school year can appear in several documents
        seen_years.add(year)
        for vac in node["vacations"] or []:
            label = str(vac.get("type", "")).strip()
            compulsory = str(vac.get("compulsorydates", "true")).strip().lower() != "false"
            for reg in vac.get("regions") or []:
                region = str(reg.get("region", "")).strip().lower()
                targets = list(NL_REGIONS) if region in ("heel nederland", "nederland", "heel land") else [region]
                start = local_date(reg["startdate"], "Europe/Amsterdam")
                end = local_date(reg["enddate"], "Europe/Amsterdam")
                for t in targets:
                    if t not in NL_REGIONS:
                        raise ValueError(f"unknown NL region {region!r}")
                    c = cals.setdefault((t, year), dict(
                        country_code="NL", subdivision_code=None, authority=NL_REGIONS[t], authority_kind="other",
                        school_year=year, periods=[], notes=[],
                        source_url="https://www.rijksoverheid.nl/onderwerpen/schoolvakanties"))
                    c["periods"].append(dict(start_date=start, end_date=end, kind="break", label=label,
                                             names={"nl": label}))
                    if not compulsory:
                        c["notes"].append(f"{label}: dates are advisory (compulsorydates=false)")
    return list(cals.values())


# ------------------------------------------------------------------ France

FR_URLS = [
    "https://data.education.gouv.fr/api/explore/v2.1/catalog/datasets/fr-en-calendrier-scolaire/exports/json",
    "https://data.education.gouv.fr/api/records/1.0/search/?dataset=fr-en-calendrier-scolaire&rows=10000",
]
# zone -> (subdivision code or None, authority name or None, time zone)
FR_ZONES = {
    "zone a": (None, "Zone A", "Europe/Paris"),
    "zone b": (None, "Zone B", "Europe/Paris"),
    "zone c": (None, "Zone C", "Europe/Paris"),
    "corse": (None, "Corse", "Europe/Paris"),
    "guadeloupe": ("FR-971", None, "America/Guadeloupe"),
    "martinique": ("FR-972", None, "America/Martinique"),
    "guyane": ("FR-973", None, "America/Cayenne"),
    "la reunion": ("FR-974", None, "Indian/Reunion"),
    "reunion": ("FR-974", None, "Indian/Reunion"),
    "mayotte": ("FR-976", None, "Indian/Mayotte"),
    "polynesie": ("FR-PF", None, "Pacific/Tahiti"),
    "polynesie francaise": ("FR-PF", None, "Pacific/Tahiti"),
    "nouvelle caledonie": ("FR-NC", None, "Pacific/Noumea"),
    "saint pierre et miquelon": ("FR-PM", None, "America/Miquelon"),
    "wallis et futuna": ("FR-WF", None, "Pacific/Wallis"),
}
FR_LABELS = [  # (pattern on normalised description, label, kind)
    ("toussaint", "Toussaint", "break"),
    ("noel", "Noël", "break"),
    ("hiver", "Hiver", "break"),
    ("printemps", "Printemps", "break"),
    ("ascension", "Pont de l'Ascension", "holiday"),
    ("ete", "Été", "break"),
    ("carnaval", "Carnaval", "break"),
    ("austral", "Vacances australes", "break"),
    ("cyclone", "Vacances", "break"),
]


def _fr_records(raw: bytes) -> list[dict]:
    data = json.loads(raw)
    if isinstance(data, dict) and "records" in data:  # v1 search API
        return [r.get("fields", r) for r in data["records"]]
    if isinstance(data, dict) and "results" in data:
        return data["results"]
    return data


def adapter_fr(raw: bytes) -> list[dict]:
    """French dates mark 'after classes' (start) and 'classes resume' (end): free days are start+1 .. end-1."""
    cals: dict[tuple, dict] = {}
    unknown = Counter()
    seen = set()
    for r in _fr_records(raw):
        desc = str(r.get("description") or "").strip()
        pop = norm(str(r.get("population") or "-"))
        zone = norm(str(r.get("zones") or ""))
        if zone not in FR_ZONES:
            unknown[f"zone {r.get('zones')}"] += 1
            continue
        sub, auth, tz = FR_ZONES[zone]
        if not r.get("start_date") or not r.get("annee_scolaire"):
            continue
        key = (zone, desc, pop, r["start_date"], r.get("end_date"))
        if key in seen:
            continue  # the dataset repeats every period once per académie
        seen.add(key)
        year = school_year(str(r["annee_scolaire"]))
        c = cals.setdefault((zone, year), dict(
            country_code="FR", subdivision_code=sub, authority=auth, authority_kind="other", school_year=year,
            periods=[], notes=[], first_day=None, last_day=None,
            source_url="https://www.education.gouv.fr/calendrier-scolaire-100148"))
        start = local_date(r["start_date"], tz)
        end = local_date(r["end_date"], tz) if r.get("end_date") else None
        d = norm(desc)
        if "rentree" in d:
            if "enseignant" in d or "enseignant" in pop:
                c["periods"].append(dict(start_date=start, end_date=start, kind="teacher_day",
                                         label="Prérentrée des enseignants", names={"fr": "Prérentrée des enseignants"}))
            else:
                c["first_day"] = start
            continue
        if "enseignant" in pop:
            continue
        if d.startswith("debut des vacances") and (end is None or end == start):
            c["last_day"] = start  # summer end not yet published
            continue
        label, kind = next(((lbl, k) for pat, lbl, k in FR_LABELS if re.search(rf"\b{pat}\b", d)), (desc, "break"))
        if end is None:
            unknown[f"no end: {desc}"] += 1
            continue
        first, last = start + dt.timedelta(days=1), end - dt.timedelta(days=1)
        if last < first:
            unknown[f"empty: {desc} {start}"] += 1
            continue
        if label == "Été":
            c["last_day"] = c["last_day"] or start
        c["periods"].append(dict(start_date=first, end_date=last, kind=kind, label=label, names={"fr": desc}))
    if unknown:
        print("FR skipped:", dict(unknown))
    return list(cals.values())


ADAPTERS = {
    "nl": ("rijksoverheid-nl", [NL_URL], adapter_nl, "nl.json"),
    "fr": ("education-gouv-fr", FR_URLS, adapter_fr, "fr.json"),
}


# ------------------------------------------------------------------ database

def authority_id(cur, c: dict, source_id: str) -> str | None:
    if not c.get("authority"):
        return None
    cur.execute("select id::text from public.education_authorities where country_code = %s and name = %s order by source_id = 'editorial' desc limit 1",
                (c["country_code"], c["authority"]))
    row = cur.fetchone()
    if row:
        return row[0]
    new = str(uuid.uuid5(OFFICIAL_NS, f"authority|{c['country_code']}|{c['authority']}"))
    cur.execute("""insert into public.education_authorities (id, country_code, subdivision_code, kind, name, source_id)
                   values (%s, %s, %s, %s, %s, %s) on conflict (id) do nothing""",
                (new, c["country_code"], c["subdivision_code"], c["authority_kind"], c["authority"], source_id))
    return new


def compare(cur, cal_id_editorial: str, periods: list[dict]) -> tuple[int, int, list[str]]:
    """Compare multi-day breaks by label. Returns (compared, mismatched, notes)."""
    cur.execute("select label, start_date, end_date from public.school_calendar_periods where calendar_id = %s and kind = 'break'",
                (cal_id_editorial,))
    ed = defaultdict(list)
    for label, s, e in cur.fetchall():
        ed[norm(label)].append((s, e))
    compared = mismatched = 0
    notes = []
    for p in periods:
        if p["kind"] != "break":
            continue
        cands = ed.get(norm(p["label"]))
        if not cands:
            continue
        compared += 1
        if (p["start_date"], p["end_date"]) not in cands:
            mismatched += 1
            notes.append(f"{p['label']}: official {p['start_date']}..{p['end_date']}, research "
                         + ", ".join(f"{s}..{e}" for s, e in cands))
    return compared, mismatched, notes


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="write even if the comparison with research data disagrees")
    ap.add_argument("--only", default="", help="comma list of adapters (nl,fr)")
    ap.add_argument("--fixture", help="directory with nl.json / fr.json instead of downloading")
    args = ap.parse_args()
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("DATABASE_URL is not set")
        return 2
    import psycopg
    from psycopg.types.json import Jsonb

    wanted = [a.strip() for a in args.only.split(",") if a.strip()] or list(ADAPTERS)
    retrieved = dt.datetime.now(dt.timezone.utc)
    lines = [f"## Official school holiday import {'(dry run)' if args.dry_run else ''}", ""]
    exit_code = 0

    with psycopg.connect(dsn) as conn:
        for key in wanted:
            source_id, urls, adapter, fixture_name = ADAPTERS[key]
            stats = Counter()
            # 1. download + parse; on any error keep the last good data
            raw, calendars = None, []
            candidates = [os.path.join(args.fixture, fixture_name)] if args.fixture else urls
            for u in candidates:
                try:
                    raw = open(u, "rb").read() if args.fixture else http_get(u)
                    calendars = adapter(raw)
                    if calendars:
                        break
                except Exception as e:
                    print(f"{key}: {u} failed: {type(e).__name__}: {e}")
                    calendars = []
            if not calendars:
                lines += [f"### {key}: no data, nothing changed", ""]
                exit_code = 1
                continue
            digest = __import__("hashlib").sha256(raw).hexdigest()[:16]

            with conn.cursor() as cur:
                cur.execute("""insert into public.sources (id, name, url, license, share_alike, attribution)
                               values (%(id)s, %(name)s, %(url)s, %(license)s, false, %(attribution)s)
                               on conflict (id) do nothing""", dict(SOURCES[source_id], id=source_id))
                mism_notes: list[str] = []
                superseded = []
                for c in calendars:
                    c["periods"].sort(key=lambda p: (p["start_date"], p["label"]))
                    auth = authority_id(cur, c, source_id)
                    cid = str(uuid.uuid5(OFFICIAL_NS, f"{source_id}|{c['country_code']}|{c['subdivision_code'] or ''}|{auth or ''}|{c['school_year']}"))
                    notes = "; ".join(dict.fromkeys(c["notes"])) or None
                    cur.execute(
                        """insert into public.school_calendars
                             (id, country_code, subdivision_code, authority_id, school_year, title, origin, status,
                              source_id, source_version, source_url, source_retrieved_at, first_day, last_day, notes)
                           values (%s, %s, %s, %s, %s, %s, 'official', 'confirmed', %s, %s, %s, %s, %s, %s, %s)
                           on conflict (id) do update set
                             status = 'confirmed', source_version = excluded.source_version, source_url = excluded.source_url,
                             source_retrieved_at = excluded.source_retrieved_at, first_day = excluded.first_day,
                             last_day = excluded.last_day, notes = excluded.notes, title = excluded.title
                           returning (xmax = 0)""",
                        (cid, c["country_code"], c["subdivision_code"], auth, c["school_year"],
                         c["authority"] or c["subdivision_code"], source_id, f"sha256:{digest}", c["source_url"],
                         retrieved, c.get("first_day"), c.get("last_day"), notes))
                    stats["calendars_new" if cur.fetchone()[0] else "calendars_updated"] += 1
                    cur.execute("delete from public.school_calendar_periods where calendar_id = %s", (cid,))
                    for p in c["periods"]:
                        cur.execute(
                            """insert into public.school_calendar_periods (calendar_id, start_date, end_date, kind, label, names)
                               values (%s, %s, %s, %s, %s, %s)
                               on conflict on constraint school_calendar_periods_natural_key do update set kind = excluded.kind, names = excluded.names""",
                            (cid, p["start_date"], p["end_date"], p["kind"], p["label"], Jsonb(p["names"])))
                        stats["periods"] += 1
                    # 2. research calendars for the same scope and year: compare, then supersede
                    cur.execute(
                        """select id::text from public.school_calendars
                            where origin in ('editorial', 'community') and status in ('confirmed', 'pending', 'outdated')
                              and country_code = %s and school_year = %s
                              and subdivision_code is not distinct from %s and authority_id is not distinct from %s""",
                        (c["country_code"], c["school_year"], c["subdivision_code"], auth))
                    for (old,) in cur.fetchall():
                        n, bad, notes_ = compare(cur, old, c["periods"])
                        stats["breaks_compared"] += n
                        stats["breaks_mismatched"] += bad
                        mism_notes += [f"{c['authority'] or c['subdivision_code']} {c['school_year']}: {x}" for x in notes_]
                        superseded.append(old)
                    stats["years_" + c["school_year"]] += 1

                ratio = stats["breaks_mismatched"] / stats["breaks_compared"] if stats["breaks_compared"] else 0.0
                blocked = ratio > MAX_MISMATCH_RATIO and not args.force
                if superseded and not blocked:
                    cur.execute("""update public.school_calendars
                                      set status = 'outdated',
                                          notes = trim(both ' ' from coalesce(notes, '') || ' Superseded by official data (' || %s || ').')
                                    where id = any(%s::uuid[]) and status <> 'outdated'""", (source_id, superseded))
                    stats["research_superseded"] = cur.rowcount

                years = sorted(k[6:] for k in stats if k.startswith("years_"))
                lines += [f"### {key} ({source_id})", "",
                          f"- school years: {', '.join(years)}",
                          *[f"- {k}: {v}" for k, v in sorted(stats.items()) if not k.startswith("years_")],
                          f"- agreement with research data: {stats['breaks_compared'] - stats['breaks_mismatched']}"
                          f"/{stats['breaks_compared']} breaks identical"]
                if mism_notes:
                    lines += ["", "Differences:", *[f"- {m}" for m in mism_notes[:60]]]
                if blocked:
                    lines += ["", f"**Aborted: {ratio:.0%} of compared breaks differ (limit {MAX_MISMATCH_RATIO:.0%}). "
                                  "Nothing written for this source. Check the differences, then run with force.**"]
                    exit_code = 1
                lines.append("")
            if blocked or args.dry_run:
                conn.rollback()
            else:
                conn.commit()

    summary = "\n".join(lines) + ("\nDry run: rolled back.\n" if args.dry_run else "")
    print(summary)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
            f.write(summary)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
