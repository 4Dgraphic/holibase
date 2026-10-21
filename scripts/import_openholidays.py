"""
Import school holidays from the OpenHolidays API data (https://www.openholidaysapi.org).

    DATABASE_URL=postgresql://... python scripts/import_openholidays.py [--dry-run] [--only de,at,ch] [--source DIR]

Data: github.com/openpotato/openholidaysapi.data (CSV files per country), licence ODbL 1.0 (share-alike).
The calendars are kept as their own layer (source_id 'openholidays', origin 'library') and the API reports
their licence per calendar. Precedence (see migration 20261017120000_openholidays.sql): official, editorial
and community calendars, and python-holidays, win over OpenHolidays for the same scope and school year.
OpenHolidays fills the gaps: school years and regions nobody else covers.

How it works
  * Downloads the repository as one tarball (no API, no rate limit) and reads src/<country>/.
  * Countries with official open data in Holibase (France, Netherlands) are skipped; Belgium is skipped
    until its communities are mapped to Holibase authorities.
  * One calendar per region and school year. Nationwide periods are added to every region of the country.
    Only school types for general/primary education are used (Swiss "Volksschulen", German "allgemeinbildende Schulen").
  * A school year needs at least MIN_BREAKS breaks and must reach past February; partial years are left out
    rather than shown incomplete.
  * Local variants (a canton's regions or districts, rows that differ only by a comment such as "Tourismusgemeinden")
    are not mixed: the region gets the calendar that applies to most of it (see main_variant()).
  * Regions that Holibase does not know yet (for example Czech districts) are added to subdivisions.
  * Calendars that disappeared from the source are marked 'outdated'. A country whose calendar count drops
    by more than half is skipped (the source format probably changed); the last good data stays.
  * The job summary lists how well OpenHolidays agrees with the calendars Holibase already has.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import io
import os
import re
import sys
import tarfile
import urllib.request
import uuid
from collections import Counter, defaultdict

TARBALL = "https://codeload.github.com/openpotato/openholidaysapi.data/tar.gz/refs/heads/main"
NS = uuid.UUID("5b0c8f3e-2d7a-4c41-9e6b-7a1f0d3c8e25")
SOURCE_ID = "openholidays"
UA = "holibase-import/1.0 (+https://holibase.org)"
MIN_BREAKS = 3
FIRST_YEAR = 2019
SKIP = {"fr": "official open data in Holibase", "nl": "official open data in Holibase",
        "be": "communities not mapped to Holibase authorities yet"}
CALENDAR_YEAR = {"za"}  # school year = calendar year
PRIMARY_GROUPS = ("primary", "compulsory", "general")  # English group names to keep
SOURCE_PAGES = {"za": "https://www.openholidaysapi.org/en/sources-africa/", "mx": "https://www.openholidaysapi.org/en/sources-americas/",
                "br": "https://www.openholidaysapi.org/en/sources-americas/"}


def read_csv(text: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO(text.lstrip("﻿")), delimiter=";"))


def names(field: str) -> dict:
    """'DE Weihnachtsferien,EN Christmas Holidays' -> {'de': 'Weihnachtsferien', 'en': 'Christmas Holidays'}"""
    out = {}
    for part in re.split(r",(?=[A-Z]{2} )", field or ""):
        m = re.match(r"([A-Z]{2}) (.+)", part.strip())
        if m:
            out[m.group(1).lower()] = m.group(2).strip()
    return out


def parse_date(s: str) -> dt.date | None:
    """Lenient: '2029-04-4' is read as 2029-04-04; empty or broken values give None."""
    m = re.fullmatch(r"\s*(\d{4})-(\d{1,2})-(\d{1,2})\s*", s or "")
    if not m:
        return None
    try:
        return dt.date(*map(int, m.groups()))
    except ValueError:
        return None


def listing(field: str | None) -> list[str]:
    return [x.strip() for x in (field or "").split(",") if x.strip()]


def school_year(cc: str, start: dt.date, en_name: str) -> str:
    if cc in CALENDAR_YEAR:
        return str(start.year)
    if "summer" in en_name.lower():  # the summer break ends the school year, even when it starts in August
        y = start.year - 1
    else:
        y = start.year if start.month >= 8 else start.year - 1
    return f"{y}-{(y + 1) % 100:02d}"


def load_files(source: str | None) -> dict[str, str]:
    """{'de/holidays/holidays.school.ni.csv': text, ...}"""
    files = {}
    if source:
        for root, _, fs in os.walk(source):
            for f in fs:
                if f.endswith(".csv"):
                    p = os.path.join(root, f)
                    files[os.path.relpath(p, source).replace(os.sep, "/")] = open(p, encoding="utf-8").read()
        return files
    req = urllib.request.Request(TARBALL, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=180) as r:
        data = r.read()
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        for m in tar.getmembers():
            if m.isfile() and m.name.endswith(".csv") and "/src/" in m.name:
                rel = m.name.split("/src/", 1)[1]
                files[rel] = tar.extractfile(m).read().decode("utf-8")
    return files


MAIN = re.compile(r"Volksschul|Alle Schulen|obligatoire|Obligatorische", re.I)
EXCEPTION = re.compile(r"^(DE |FR |IT )?(Ausnahme|Exception|Eccezione|Tourismusgemeinden|Communes touristiques)|Mittelschul|Berufs|sec\. II", re.I)


def complete(cc: str, year: str, periods: list[dict]) -> bool:
    """A school year counts only when the source reaches into its second half: the OpenHolidays files of
    several Swiss cantons end in December, which left autumn and Christmas looking like a whole year."""
    if cc in CALENDAR_YEAR:
        return True
    second = int(year[:4]) + 1
    return any(p["start_date"] >= dt.date(second, 3, 1) for p in periods)


def main_variant(scope, rows: list[tuple], subs: dict, iso) -> list[dict]:
    """The periods of the calendar that applies to most of a region.

    OpenHolidays lists local variants in two ways: rows for smaller areas (Graubünden's regions, the districts
    of Appenzell Innerrhoden) and rows that differ only by a comment (Obwalden with and without Engelberg,
    German- and French-speaking Valais, the islands of Schleswig-Holstein). Mixing them gives overlapping
    periods. Kept: rows for the whole region, plus the rows of the largest group of smaller areas if it covers
    at least half of the region. Exceptions (islands, tourist communities, upper secondary schools) are left
    out; where two remaining variants overlap, the more frequent one wins (the region's first language on a tie)."""
    if not rows:
        return []
    short = next((k for k, v in subs.items() if v.get("IsoCode") == scope), None)
    lang = ((subs.get(short) or {}).get("OfficialLanguages") or "").split(",")[0].strip().upper()
    exception = lambda c: bool(EXCEPTION.search(c)) and not MAIN.search(c)  # noqa: E731
    kept = [r for r in rows if r[1] == "*" and not exception(r[2])]
    parts = [r for r in rows if r[1] != "*" and not exception(r[2])]
    if parts:
        groups = Counter(u for _, u, _ in parts)
        best = max(groups, key=lambda u: (len(u), groups[u]))
        total = sum(1 for v in subs.values() if v.get("Parent") == short) or len(best)
        if len(best) * 2 >= total:
            kept += [r for r in parts if r[1] == best]
    variants: dict[tuple, list[dict]] = defaultdict(list)
    for p, u, c in kept:
        variants[(u, c)].append(p)
    order = sorted(variants, key=lambda v: (len(variants[v]), v[1] == "" or v[1].upper().startswith(lang + " ")), reverse=True)
    out: list[dict] = []
    for v in order:  # a variant that clashes with a preferred one is an alternative to it, not a supplement
        ps = variants[v]
        if not any(q["start_date"] <= p["end_date"] and p["start_date"] <= q["end_date"]
                   and (q["start_date"], q["end_date"]) != (p["start_date"], p["end_date"]) for p in ps for q in out):
            out += ps
    return out


# Some cantons are listed with bare season words ("Herbst", and "Winter" for the Christmas break) and one with
# a typo; they get the names the cantons themselves use. Keyed by the English name of a multi-day period.
FULL_NAMES = {
    "autumn": {"de": "Herbstferien", "fr": "Vacances d'automne", "it": "Vacanze d'autunno", "en": "Autumn holidays"},
    "christmas": {"de": "Weihnachtsferien", "fr": "Vacances de Noël", "it": "Vacanze di Natale", "en": "Christmas holidays"},
    "sport": {"de": "Sportferien", "fr": "Vacances sportives", "it": "Vacanze sportive", "en": "Sports holidays"},
    "spring": {"de": "Frühlingsferien", "fr": "Vacances de printemps", "it": "Vacanze di primavera", "en": "Spring holidays"},
    "easter": {"de": "Osterferien", "fr": "Vacances de Pâques", "it": "Vacanze di Pasqua", "en": "Easter holidays"},
    "summer": {"de": "Sommerferien", "fr": "Vacances d'été", "it": "Vacanze estive", "en": "Summer holidays"},
}


def tidy_names(n: dict, multi_day: bool) -> dict:
    full = FULL_NAMES.get(n.get("en", "").strip().lower()) if multi_day else None
    if full:
        return {k: full.get(k, v) for k, v in n.items()}
    return {k: ("Osterferien" if v == "Osternferien" else v) for k, v in n.items()}


def parse_country(cc: str, files: dict[str, str]) -> tuple[dict, dict]:
    """Returns (calendars, subdivisions). calendars: {(sub_code|None, school_year): [period, ...]}"""
    subs = {r["ShortName"]: r for r in read_csv(files.get(f"{cc}/subdivisions.csv", ""))}
    groups = {r["ShortName"]: r for r in read_csv(files.get(f"{cc}/groups.csv", ""))}

    def iso(short: str) -> str | None:
        r = subs.get(short)
        return (r.get("IsoCode") or None) if r else None

    national, regional = [], defaultdict(list)
    for path, text in files.items():
        if not path.startswith(f"{cc}/holidays/holidays.school"):
            continue
        for r in read_csv(text):
            if r.get("Type", "School") != "School" or r.get("RegionalScope") == "Local":
                continue
            gs = listing(r.get("Groups"))
            if gs and not any(any(k in names(groups.get(g, {}).get("Name", "")).get("en", "").lower() for k in PRIMARY_GROUPS) for g in gs):
                continue
            start, end = parse_date(r.get("StartDate")), parse_date(r.get("EndDate"))
            if not start or not end or end < start or end.year < FIRST_YEAR:
                continue
            n = tidy_names(names(r.get("Name", "")), (end - start).days >= 1)
            lang = (listing((subs.get(listing(r.get("Subdivisions"))[0]) or {}).get("OfficialLanguages")) if listing(r.get("Subdivisions")) else [])
            label = next((n[l.lower()] for l in lang if l.lower() in n), None) or next(iter(n.values()), "School holiday")
            period = dict(start_date=start, end_date=end, label=label, names=n,
                          kind="break" if (end - start).days >= 1 else "holiday",
                          school_year=school_year(cc, start, n.get("en", label)))
            ss = listing(r.get("Subdivisions"))
            if not ss and gs:  # e.g. Mecklenburg-Vorpommern lists only its school type 'MV-ABS'
                ss = sorted({g.split("-")[0] for g in gs if g.split("-")[0] in subs})
            if not ss:
                if r.get("RegionalScope") == "National":
                    national.append(period)
                continue
            comment = re.sub(r"\s*\(\d\d\.\d\d\.\d{4}-\d\d\.\d\d\.\d{4}\)", "", (r.get("Comment") or "").replace("%2C", ","))
            comment = comment.split(",EN ")[0].strip()
            units: dict[str, list[str]] = defaultdict(list)  # Holibase region -> the source's smaller areas (district, municipality)
            for s in ss:
                code = iso(s)
                if code:
                    units[code].append("*")  # the whole region
                    continue
                parent = (subs.get(s) or {}).get("Parent")
                while parent and not iso(parent):
                    parent = (subs.get(parent) or {}).get("Parent")
                if parent:
                    units[iso(parent)].append(s)
            for code, us in units.items():
                regional[code].append((period, "*" if "*" in us else frozenset(us), comment))

    calendars = defaultdict(list)
    scopes = list(regional) or [None]
    for scope in scopes:
        for p in national + main_variant(scope, regional.get(scope, []), subs, iso):
            calendars[(scope, p["school_year"])].append(p)
    out = {}
    for key, ps in calendars.items():
        uniq = {(p["start_date"], p["end_date"], p["label"]): p for p in ps}
        ps = sorted(uniq.values(), key=lambda p: (p["start_date"], p["end_date"]))
        if sum(p["kind"] == "break" for p in ps) >= MIN_BREAKS and complete(cc, key[1], ps):
            out[key] = ps

    needed = {}
    for short, r in subs.items():
        code = r.get("IsoCode")
        if code and code in regional:
            parent = iso(r["Parent"]) if r.get("Parent") else None
            n = names(r.get("Name", ""))
            langs = [l.lower() for l in listing(r.get("OfficialLanguages"))]
            needed[code] = dict(code=code, country_code=cc.upper(), parent_code=parent, source_code=r.get("Code"),
                                name=next((n[l] for l in langs if l in n), None) or n.get("en") or short, names=n,
                                kind=names(r.get("Category", "")).get("en"))
    return out, needed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only", default="", help="comma list of country codes, e.g. de,at,ch")
    ap.add_argument("--source", help="local checkout of openholidaysapi.data/src instead of downloading")
    args = ap.parse_args()
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("DATABASE_URL is not set")
        return 2
    import psycopg
    from psycopg.types.json import Jsonb

    try:
        files = load_files(args.source)
    except Exception as e:  # keep the last good data
        print(f"download failed: {type(e).__name__}: {e}")
        return 1
    digest = hashlib.sha256("".join(sorted(files)).encode() + b"".join(files[k].encode() for k in sorted(files))).hexdigest()[:16]
    countries = sorted({p.split("/")[0] for p in files if "/holidays/holidays.school" in p})
    only = {c.strip().lower() for c in args.only.split(",") if c.strip()}
    retrieved = dt.datetime.now(dt.timezone.utc)
    lines = [f"## OpenHolidays import {'(dry run)' if args.dry_run else ''}", "",
             f"Source: {TARBALL} (sha256 {digest}), licence ODbL 1.0", "",
             "| Country | Calendars | New | Updated | Outdated | School years | Agreement with Holibase |", "|---|---|---|---|---|---|---|"]
    notes, exit_code = [], 0

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("select code from public.countries")
        known_countries = {r[0] for r in cur.fetchall()}
        cur.execute("select code from public.subdivisions")
        known_subs = {r[0] for r in cur.fetchall()}
        for cc in countries:
            if only and cc not in only:
                continue
            if cc in SKIP:
                notes.append(f"- {cc.upper()}: skipped ({SKIP[cc]})")
                continue
            if cc.upper() not in known_countries:
                notes.append(f"- {cc.upper()}: skipped (country not in Holibase)")
                continue
            try:
                calendars, subs = parse_country(cc, files)
            except Exception as e:
                notes.append(f"- {cc.upper()}: parse error, nothing changed ({type(e).__name__}: {e})")
                exit_code = 1
                continue
            cur.execute("select count(*) from public.school_calendars where source_id = %s and country_code = %s and status = 'confirmed'",
                        (SOURCE_ID, cc.upper()))
            before = cur.fetchone()[0]
            if before and len(calendars) < before / 2:
                notes.append(f"- {cc.upper()}: only {len(calendars)} calendars, had {before}; skipped (source format change?)")
                exit_code = 1
                continue
            if not calendars:
                notes.append(f"- {cc.upper()}: no complete school year in the source")
                continue

            for code, s in subs.items():
                if code in known_subs:
                    continue
                if s["parent_code"] and s["parent_code"] not in known_subs:
                    s["parent_code"] = None
                cur.execute("""insert into public.subdivisions (code, country_code, parent_code, source_code, name, names, kind, iso_verified)
                               values (%(code)s, %(country_code)s, %(parent_code)s, %(source_code)s, %(name)s, %(names)s, %(kind)s, false)
                               on conflict (code) do nothing""", dict(s, names=Jsonb(s["names"])))
                known_subs.add(code)

            stats = Counter()
            kept_ids = []
            source_url = SOURCE_PAGES.get(cc, "https://www.openholidaysapi.org/en/sources-europe/")
            for (sub, sy), periods in sorted(calendars.items(), key=lambda kv: (kv[0][0] or "", kv[0][1])):
                if sub and sub not in known_subs:
                    stats["skipped_unknown_region"] += 1
                    continue
                cid = str(uuid.uuid5(NS, f"{SOURCE_ID}|{cc.upper()}|{sub or ''}|{sy}"))
                kept_ids.append(cid)
                cur.execute(
                    """insert into public.school_calendars
                         (id, country_code, subdivision_code, authority_id, school_year, title, origin, status,
                          source_id, source_version, source_url, source_retrieved_at)
                       values (%s, %s, %s, null, %s, %s, 'library', 'confirmed', %s, %s, %s, %s)
                       on conflict (id) do update set status = 'confirmed', source_version = excluded.source_version,
                         source_url = excluded.source_url, source_retrieved_at = excluded.source_retrieved_at
                       returning (xmax = 0)""",
                    (cid, cc.upper(), sub, sy, sub or cc.upper(), SOURCE_ID, f"sha256:{digest}", source_url, retrieved))
                stats["new" if cur.fetchone()[0] else "updated"] += 1
                cur.execute("delete from public.school_calendar_periods where calendar_id = %s", (cid,))
                cur.executemany("""insert into public.school_calendar_periods (calendar_id, start_date, end_date, kind, label, names)
                                   values (%s, %s, %s, %s, %s, %s) on conflict on constraint school_calendar_periods_natural_key do nothing""",
                                [(cid, p["start_date"], p["end_date"], p["kind"], p["label"], Jsonb(p["names"])) for p in periods])
                stats["years_" + sy] += 1

                # agreement with a better calendar for the same scope and year (information only)
                cur.execute("""select o.id from public.school_calendars o
                                where o.status = 'confirmed' and o.country_code = %s and o.school_year = %s
                                  and o.subdivision_code is not distinct from %s and o.authority_id is null
                                  and public.calendar_rank(o.origin, o.source_id) < public.calendar_rank('library', %s)
                                order by public.calendar_rank(o.origin, o.source_id) limit 1""", (cc.upper(), sy, sub, SOURCE_ID))
                other = cur.fetchone()
                if other:
                    cur.execute("select start_date, end_date from public.school_calendar_periods where calendar_id = %s and kind = 'break'", (other[0],))
                    theirs = {(s, e) for s, e in cur.fetchall()}
                    for p in periods:
                        if p["kind"] != "break":
                            continue
                        stats["compared"] += 1
                        if (p["start_date"], p["end_date"]) in theirs:
                            stats["agree"] += 1
                        elif any(s <= p["end_date"] and e >= p["start_date"] for s, e in theirs):
                            stats["shifted"] += 1
                        else:
                            stats["missing_elsewhere"] += 1

            cur.execute("""update public.school_calendars set status = 'outdated',
                                  notes = trim(both ' ' from coalesce(notes, '') || ' No longer in the OpenHolidays data.')
                            where source_id = %s and country_code = %s and status = 'confirmed' and not (id = any(%s::uuid[]))""",
                        (SOURCE_ID, cc.upper(), kept_ids))
            stats["outdated"] = cur.rowcount
            years = sorted(k[6:] for k in stats if k.startswith("years_"))
            agree = (f"{stats['agree']}/{stats['compared']} breaks identical"
                     + (f", {stats['shifted']} with other dates" if stats["shifted"] else "")) if stats["compared"] else "–"
            lines.append(f"| {cc.upper()} | {stats['new'] + stats['updated']} | {stats['new']} | {stats['updated']} | {stats['outdated']} | "
                         f"{years[0] if years else ''} to {years[-1] if years else ''} | {agree} |")
            if stats["skipped_unknown_region"]:
                notes.append(f"- {cc.upper()}: {stats['skipped_unknown_region']} calendars for unknown regions skipped")

        if args.dry_run:
            conn.rollback()
        else:
            conn.commit()

    summary = "\n".join(lines + ([""] + notes if notes else []) + ["", "Dry run: rolled back." if args.dry_run else ""]) + "\n"
    print(summary)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
            f.write(summary)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
