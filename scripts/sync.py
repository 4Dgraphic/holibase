"""
Sync the library data (python-holidays) into the Holibase database.

    DATABASE_URL=postgresql://... python scripts/sync.py [--dry-run] [--force]
        [--from-year 2020] [--horizon 10] [--countries DE,US] [--max-delete-ratio 0.05]

What it does, in one transaction:
  1. Builds public holidays and school calendars for the window from-year .. current year + horizon.
  2. Inserts what is new, updates what changed (names, flags, scope), deletes library rows inside
     the window that the source no longer delivers (abolished holidays, corrected dates).
     Rows before the window are never touched, so history is kept.
  3. Adds countries / subdivisions that the source introduced.
  4. Writes a summary (stdout + $GITHUB_STEP_SUMMARY).

Only rows with source_id = 'python-holidays' (and library school calendars) are touched;
editorial and community data is never modified.

Safety: aborts when it would delete more than --max-delete-ratio of the rows in the window
(protects against a broken library release). --dry-run rolls back at the end.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
import warnings
from collections import Counter, defaultdict

import psycopg

sys.path.insert(0, os.path.dirname(__file__))
import build  # noqa: E402

SRC = build.SOURCE_ID
# python-holidays warns when a country's rules end before the requested year (e.g. "only until 2035").
warnings.filterwarnings("ignore", message="Requested Holidays are available only")


def log(msg: str) -> None:
    print(msg, flush=True)


# ------------------------------------------------------------------ data collection

def collect(countries: list[str], years: list[int]):
    infos, ph_rows, calendars = [], [], []
    for info, ph, sc in build.build(countries, years):
        infos.append(info)
        ph_rows.extend(ph)
        calendars.extend(sc)
    return infos, ph_rows, calendars


# ------------------------------------------------------------------ database steps

def sync_reference(cur, infos, ph_rows, calendars) -> dict:
    out = {"countries_added": [], "subdivisions_added": []}
    for info in infos:
        cats = info["categories"]
        langs = [build.lang_tag(l) for l in info["languages"]]
        default = build.lang_tag(info["default_language"]) if info["default_language"] else "en"
        cur.execute(
            """insert into public.countries (code, default_language, languages, holiday_categories)
               values (%s, %s, %s, %s)
               on conflict (code) do update
                 set default_language = excluded.default_language,
                     languages = excluded.languages,
                     holiday_categories = excluded.holiday_categories
               where (countries.default_language, countries.languages, countries.holiday_categories)
                     is distinct from (excluded.default_language, excluded.languages, excluded.holiday_categories)
               returning (xmax = 0) as inserted""",
            (info["code"], default, langs, cats),
        )
        r = cur.fetchone()
        if r and r[0]:
            out["countries_added"].append(info["code"])

    subs = {}
    for r in ph_rows:
        if r["subdivision_code"]:
            subs[r["subdivision_code"]] = r["country_code"]
    for c in calendars:
        if c["subdivision_code"]:
            subs[c["subdivision_code"]] = c["country_code"]
    for code, cc in sorted(subs.items()):
        source_code = code.split("-", 1)[1]
        cur.execute(
            """insert into public.subdivisions (code, country_code, source_code, name)
               values (%s, %s, %s, %s) on conflict (code) do nothing returning code""",
            (code, cc, source_code, source_code),
        )
        if cur.fetchone():
            out["subdivisions_added"].append(code)
    return out


def sync_public_holidays(cur, rows, countries, d_from, d_to, version) -> dict:
    cur.execute(
        """create temp table stage_ph (
             country_code char(2), subdivision_code text, date date, category text, scope text,
             local_name text, default_language text, names jsonb, is_observed bool, is_estimated bool
           ) on commit drop"""
    )
    with cur.copy("copy stage_ph from stdin") as cp:
        for r in rows:
            cp.write_row((r["country_code"], r["subdivision_code"], r["date"], r["category"], r["scope"],
                          r["local_name"], r["default_language"], json.dumps(r["names"], ensure_ascii=False),
                          r["is_observed"], r["is_estimated"]))
    cur.execute("create index on stage_ph (country_code, coalesce(subdivision_code, ''), date, category, local_name)")
    cur.execute("analyze stage_ph")

    key = """p.country_code = s.country_code and coalesce(p.subdivision_code, '') = coalesce(s.subdivision_code, '')
             and p.date = s.date and p.category = s.category and p.local_name = s.local_name"""
    scope = "p.source_id = %(src)s and p.date between %(f)s and %(t)s and p.country_code = any(%(cc)s)"
    params = {"src": SRC, "f": d_from, "t": d_to, "cc": countries, "v": version}

    cur.execute(f"select count(*) from public.public_holidays p where {scope}", params)
    in_window = cur.fetchone()[0]

    cur.execute(
        f"""delete from public.public_holidays p
             where {scope}
               and not exists (select 1 from stage_ph s where {key})
         returning p.country_code""",
        params,
    )
    deleted = Counter(r[0] for r in cur.fetchall())

    cur.execute(
        f"""update public.public_holidays p
               set scope = s.scope, default_language = s.default_language, names = s.names,
                   is_observed = s.is_observed, is_estimated = s.is_estimated, source_version = %(v)s
              from stage_ph s
             where {key} and p.source_id = %(src)s
               and (p.scope, p.default_language, p.names, p.is_observed, p.is_estimated)
                   is distinct from (s.scope, s.default_language, s.names, s.is_observed, s.is_estimated)
         returning p.country_code""",
        params,
    )
    changed = Counter(r[0] for r in cur.fetchall())

    cur.execute(
        f"""insert into public.public_holidays
              (country_code, subdivision_code, date, category, scope, local_name, default_language, names,
               is_observed, is_estimated, source_id, source_version)
            select s.country_code, s.subdivision_code, s.date, s.category, s.scope, s.local_name,
                   s.default_language, s.names, s.is_observed, s.is_estimated, %(src)s, %(v)s
              from stage_ph s
             where not exists (select 1 from public.public_holidays p where {key} and p.source_id = %(src)s)
         returning country_code""",
        params,
    )
    inserted = Counter(r[0] for r in cur.fetchall())

    cur.execute(
        f"""update public.public_holidays p set source_version = %(v)s
             where {scope} and p.source_version is distinct from %(v)s""",
        params,
    )
    return {"in_window": in_window, "inserted": inserted, "changed": changed, "deleted": deleted,
            "version_bumped": cur.rowcount}


def sync_school(cur, calendars, countries, d_from, d_to, version) -> dict:
    cur.execute(
        """create temp table stage_cal (
             tmp_id uuid, country_code char(2), subdivision_code text, school_year text
           ) on commit drop"""
    )
    cur.execute(
        """create temp table stage_per (
             tmp_id uuid, start_date date, end_date date, kind text, label text, names jsonb
           ) on commit drop"""
    )
    with cur.copy("copy stage_cal from stdin") as cp:
        for c in calendars:
            cp.write_row((c["id"], c["country_code"], c["subdivision_code"], c["school_year"]))
    with cur.copy("copy stage_per from stdin") as cp:
        for c in calendars:
            for p in c["periods"]:
                cp.write_row((c["id"], p["start_date"], p["end_date"], p["kind"], p["label"],
                              json.dumps(p["names"], ensure_ascii=False)))

    params = {"src": SRC, "v": version, "f": d_from, "t": d_to, "cc": countries}

    # Calendars: keep existing ids (matched on the natural key), create missing ones.
    cur.execute(
        """insert into public.school_calendars (id, country_code, subdivision_code, school_year, origin, status,
                                                source_id, source_version)
           select s.tmp_id, s.country_code, s.subdivision_code, s.school_year, 'library', 'confirmed', %(src)s, %(v)s
             from stage_cal s
           on conflict on constraint school_calendars_natural_key do nothing
           returning country_code""",
        params,
    )
    cal_added = Counter(r[0] for r in cur.fetchall())
    cur.execute(
        """create temp table cal_map on commit drop as
           select s.tmp_id, c.id
             from stage_cal s
             join public.school_calendars c
               on c.country_code = s.country_code
              and coalesce(c.subdivision_code, '') = coalesce(s.subdivision_code, '')
              and c.school_year = s.school_year and c.source_id = %(src)s
              and c.authority_id is null and c.source_url is null""",
        params,
    )
    cur.execute(
        """create temp table stage_p on commit drop as
           select m.id as calendar_id, p.start_date, p.end_date, p.kind, p.label, p.names
             from stage_per p join cal_map m using (tmp_id)"""
    )

    lib = """c.source_id = %(src)s and c.origin = 'library' and c.country_code = any(%(cc)s)"""
    pkey = """p.calendar_id = s.calendar_id and p.start_date = s.start_date and p.end_date = s.end_date
              and p.label is not distinct from s.label"""

    cur.execute(
        f"""delete from public.school_calendar_periods p
             using public.school_calendars c
             where p.calendar_id = c.id and {lib}
               and p.start_date between %(f)s and %(t)s
               and not exists (select 1 from stage_p s where {pkey})
         returning c.country_code""",
        params,
    )
    p_deleted = Counter(r[0] for r in cur.fetchall())

    cur.execute(
        f"""update public.school_calendar_periods p
               set kind = s.kind, names = s.names
              from stage_p s
             where {pkey} and (p.kind, p.names) is distinct from (s.kind, s.names)
         returning p.calendar_id""",
    )
    p_changed = cur.rowcount

    cur.execute(
        f"""insert into public.school_calendar_periods (calendar_id, start_date, end_date, kind, label, names)
            select s.calendar_id, s.start_date, s.end_date, s.kind, s.label, s.names
              from stage_p s
             where not exists (select 1 from public.school_calendar_periods p where {pkey})"""
    )
    p_inserted = cur.rowcount

    cur.execute(
        f"""delete from public.school_calendars c
             where {lib}
               and not exists (select 1 from public.school_calendar_periods p where p.calendar_id = c.id)
         returning c.country_code""",
        params,
    )
    cal_deleted = Counter(r[0] for r in cur.fetchall())

    cur.execute(
        f"""update public.school_calendars c set source_version = %(v)s
             where {lib} and c.id in (select id from cal_map) and c.source_version is distinct from %(v)s""",
        params,
    )
    return {"calendars_added": cal_added, "calendars_deleted": cal_deleted,
            "periods_inserted": p_inserted, "periods_changed": p_changed, "periods_deleted": p_deleted}


# ------------------------------------------------------------------ summary

def summary_markdown(meta, ref, ph, sc) -> str:
    lines = [
        f"## Holibase library sync {'(dry run)' if meta['dry_run'] else ''}",
        "",
        f"- python-holidays **{meta['version']}** (database before: {', '.join(meta['db_versions']) or '–'})",
        f"- Window **{meta['from']} – {meta['to']}**, {meta['countries']} countries, built in {meta['build_s']} s",
        "",
        "| | inserted | changed | deleted |",
        "|---|---:|---:|---:|",
        f"| Public holidays | {sum(ph['inserted'].values())} | {sum(ph['changed'].values())} | {sum(ph['deleted'].values())} |",
        f"| School periods | {sc['periods_inserted']} | {sc['periods_changed']} | {sum(sc['periods_deleted'].values())} |",
        f"| School calendars | {sum(sc['calendars_added'].values())} | – | {sum(sc['calendars_deleted'].values())} |",
        "",
    ]
    if ref["countries_added"] or ref["subdivisions_added"]:
        def short(xs):
            return (", ".join(xs[:30]) + (f" … (+{len(xs) - 30})" if len(xs) > 30 else "")) or "–"
        lines.append(f"New countries: {short(ref['countries_added'])}  ")
        lines.append(f"New subdivisions: {short(ref['subdivisions_added'])}")
        lines.append("")
    per = defaultdict(lambda: [0, 0, 0])
    for i, k in enumerate(("inserted", "changed", "deleted")):
        for cc, n in ph[k].items():
            per[cc][i] += n
    if per:
        lines += ["### Public holidays by country", "", "| country | inserted | changed | deleted |", "|---|---:|---:|---:|"]
        for cc, (a, b, c) in sorted(per.items(), key=lambda x: -sum(x[1]))[:40]:
            lines.append(f"| {cc} | {a} | {b} | {c} |")
        if len(per) > 40:
            lines.append(f"| … {len(per) - 40} more | | | |")
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------ main

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from-year", type=int, default=2020)
    ap.add_argument("--horizon", type=int, default=10, help="years after the current year")
    ap.add_argument("--countries", help="comma list, default: all supported")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="run even if version and window are unchanged")
    ap.add_argument("--max-delete-ratio", type=float, default=0.05)
    args = ap.parse_args()

    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        log("DATABASE_URL is not set")
        return 2

    to_year = dt.date.today().year + args.horizon
    years = list(range(args.from_year, to_year + 1))
    countries = [c.strip().upper() for c in args.countries.split(",")] if args.countries else build.supported_countries()
    d_from, d_to = dt.date(args.from_year, 1, 1), dt.date(to_year, 12, 31)
    version = build.SOURCE_VERSION

    with psycopg.connect(dsn, autocommit=False) as conn, conn.cursor() as cur:
        cur.execute("set statement_timeout = '15min'")
        cur.execute(
            """select coalesce(array_agg(distinct source_version) filter (where source_version is not null), '{}'),
                      max(date) from public.public_holidays where source_id = %s""",
            (SRC,),
        )
        db_versions, db_max = cur.fetchone()
        up_to_date = db_versions == [version] and db_max is not None and db_max.year >= to_year
        if up_to_date and not args.force and not args.countries:
            log(f"Up to date: python-holidays {version}, data until {db_max}. Nothing to do.")
            _write_summary(f"## Holibase library sync\n\nUp to date (python-holidays {version}, data until {db_max}).\n")
            return 0

        log(f"Building {len(countries)} countries, {years[0]}–{years[-1]}, python-holidays {version} …")
        t = time.time()
        infos, ph_rows, calendars = collect(countries, years)
        build_s = round(time.time() - t, 1)
        log(f"Built {len(ph_rows)} public holiday rows and {len(calendars)} school calendars in {build_s} s")

        ref = sync_reference(cur, infos, ph_rows, calendars)
        ph = sync_public_holidays(cur, ph_rows, countries, d_from, d_to, version)
        n_del = sum(ph["deleted"].values())
        if ph["in_window"] and n_del / ph["in_window"] > args.max_delete_ratio:
            conn.rollback()
            log(f"ABORT: would delete {n_del} of {ph['in_window']} rows in the window "
                f"(> {args.max_delete_ratio:.0%}). Check the library release or raise --max-delete-ratio.")
            return 3
        sc = sync_school(cur, calendars, countries, d_from, d_to, version)

        meta = {"dry_run": args.dry_run, "version": version, "db_versions": db_versions,
                "from": args.from_year, "to": to_year, "countries": len(countries), "build_s": build_s}
        md = summary_markdown(meta, ref, ph, sc)
        log(md)
        _write_summary(md)

        if args.dry_run:
            conn.rollback()
            log("Dry run: rolled back.")
        else:
            conn.commit()
            log("Committed.")
    return 0


def _write_summary(md: str) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(md)


if __name__ == "__main__":
    sys.exit(main())
