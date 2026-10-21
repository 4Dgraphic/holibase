"""
Import editorial school calendars (data/editorial/*.json) into the database.

    DATABASE_URL=postgresql://... python scripts/import_editorial.py [--dry-run] [files...]

Each file holds {"dataset", "retrieved", "method", "calendars": [...]}. Every calendar is upserted by its
id (deterministic UUID), its periods are replaced by exactly the periods in the file, and the education
authority it belongs to is created if missing. Re-running is safe; calendars not in the files are untouched.

Set-based: all rows are copied into temporary tables and merged with a handful of statements, so a few
thousand calendars take seconds even over a high-latency connection.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from collections import Counter

import psycopg

SOURCE_ID = "editorial"
GERMAN_SPEAKING = {"CH", "BE", "LU", "LI", "AT", "DE"}  # German is an official language
GLOSSARY = json.load(open(os.path.join(os.path.dirname(__file__), "..", "data", "research", "glossary.json"), encoding="utf-8"))["de"]


def with_german(cc: str, names: dict) -> dict:
    """Adds the German name from data/research/glossary.json when a period in a German-speaking country has
    none (e.g. a Geneva or Ticino calendar read in French or Italian), so lang=de shows German names."""
    if cc not in GERMAN_SPEAKING or names.get("de"):
        return names
    de = GLOSSARY.get((names.get("en") or "").strip().lower())
    return {**names, "de": de} if de else names


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    files = args.files or sorted(glob.glob(os.path.join(os.path.dirname(__file__), "..", "data", "editorial", "*.json")))
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("DATABASE_URL is not set")
        return 2

    # Collect everything first; later files win on duplicate ids.
    authorities: dict[str, tuple] = {}
    calendars: dict[str, tuple] = {}
    periods: dict[tuple, tuple] = {}
    seen_calendars: set[str] = set()
    by_key: dict[tuple, str] = {}  # same scope, year and source document -> one calendar, the later file wins
    stats = Counter()
    for path in files:
        data = json.load(open(path, encoding="utf-8"))
        for c in data["calendars"]:
            key = (c["country_code"], c["subdivision_code"], c.get("authority_id"), c["school_year"], c.get("source_url"))
            c["id"] = by_key.setdefault(key, c["id"])
            if c.get("authority_id"):
                authorities[c["authority_id"]] = (
                    c["authority_id"], c["country_code"], c["subdivision_code"], c.get("authority_kind") or "other",
                    c["authority"], json.dumps(c.get("authority_ext") or {}))
            calendars[c["id"]] = (
                c["id"], c["country_code"], c["subdivision_code"], c.get("authority_id"), c["school_year"],
                c.get("authority"), c["status"], data["dataset"], c.get("source_url"), data["retrieved"],
                c.get("first_day"), c.get("last_day"), c.get("notes"))
            stats[f"calendars_{c['status']}"] += 1
            if c["id"] in seen_calendars:  # a later file replaces the calendar, periods included
                for k in [k for k in periods if k[0] == c["id"]]:
                    del periods[k]
            seen_calendars.add(c["id"])
            for p in c["periods"]:
                periods[(c["id"], p["start_date"], p["end_date"], p["label"])] = (
                    c["id"], p["start_date"], p["end_date"], p["kind"], p["label"],
                    json.dumps(with_german(c["country_code"], p.get("names") or {}), ensure_ascii=False))

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("""
            create temp table in_auth (id uuid, country_code text, subdivision_code text, kind text, name text, ext jsonb) on commit drop;
            create temp table in_cal (id uuid, country_code text, subdivision_code text, authority_id uuid, school_year text,
                                      title text, status text, dataset text, source_url text, retrieved timestamptz,
                                      first_day date, last_day date, notes text) on commit drop;
            create temp table in_per (calendar_id uuid, start_date date, end_date date, kind text, label text, names jsonb) on commit drop;
        """)
        for table, rows in (("in_auth", authorities.values()), ("in_cal", calendars.values()), ("in_per", periods.values())):
            with cur.copy(f"copy {table} from stdin") as cp:
                for r in rows:
                    cp.write_row(r)

        # A calendar already stored under another id with the same scope, year and source document (e.g. found
        # earlier by deep research, now again by the automatic research) is updated instead of duplicated.
        cur.execute("""
            create temp table remap on commit drop as
            select distinct on (i.id) i.id as old_id, c.id as new_id
              from in_cal i join public.school_calendars c
                on c.id <> i.id and c.country_code = i.country_code
               and c.subdivision_code is not distinct from i.subdivision_code
               and c.authority_id is not distinct from i.authority_id and c.school_year = i.school_year
               and c.source_id = %s and c.source_url is not distinct from i.source_url
             where not exists (select 1 from in_cal j where j.id = c.id)""", (SOURCE_ID,))
        cur.execute("update in_per p set calendar_id = r.new_id from remap r where p.calendar_id = r.old_id")
        cur.execute("update in_cal i set id = r.new_id from remap r where i.id = r.old_id")
        cur.execute("select count(*) from remap")
        stats["calendars_matched_existing"] = cur.fetchone()[0]

        cur.execute("""
            with up as (
              insert into public.education_authorities (id, country_code, subdivision_code, kind, name, external_ids, source_id)
              select id, country_code, subdivision_code, kind, name, ext, %s from in_auth
              on conflict (id) do update set name = excluded.name,
                    -- once the NCES import set the real id, the research claim is no longer merged back in
                    external_ids = public.education_authorities.external_ids
                      || case when public.education_authorities.external_ids ? 'nces_leaid'
                              then excluded.external_ids - 'nces_leaid_claimed' else excluded.external_ids end
              returning (xmax = 0) as inserted)
            select count(*) filter (where inserted), count(*) filter (where not inserted) from up""", (SOURCE_ID,))
        stats["authorities_new"], stats["authorities_existing"] = cur.fetchone()

        cur.execute("""
            with up as (
              insert into public.school_calendars
                     (id, country_code, subdivision_code, authority_id, school_year, title, origin, status,
                      source_id, source_version, source_url, source_retrieved_at, first_day, last_day, notes)
              select id, country_code, subdivision_code, authority_id, school_year, title, 'editorial', status,
                     %s, dataset, source_url, retrieved, first_day, last_day, notes from in_cal
              on conflict (id) do update set
                     -- calendars superseded by an official source stay superseded
                     status = case when public.school_calendars.status = 'outdated'
                                        and public.school_calendars.notes like '%%Superseded by official data%%'
                                   then 'outdated' else excluded.status end,
                     source_url = excluded.source_url, source_version = excluded.source_version,
                     source_retrieved_at = excluded.source_retrieved_at, first_day = excluded.first_day,
                     last_day = excluded.last_day, title = excluded.title,
                     notes = case when public.school_calendars.notes like '%%Superseded by official data%%'
                                  then public.school_calendars.notes else excluded.notes end
              returning (xmax = 0) as inserted)
            select count(*) filter (where inserted), count(*) filter (where not inserted) from up""", (SOURCE_ID,))
        stats["calendars_new"], stats["calendars_updated"] = cur.fetchone()

        cur.execute("delete from public.school_calendar_periods where calendar_id in (select id from in_cal)")
        stats["periods_replaced"] = cur.rowcount
        cur.execute("""
            insert into public.school_calendar_periods (calendar_id, start_date, end_date, kind, label, names)
            select calendar_id, start_date, end_date, kind, label, names from in_per
            on conflict on constraint school_calendar_periods_natural_key do update set kind = excluded.kind, names = excluded.names""")
        stats["periods_written"] = cur.rowcount

        summary = "\n".join(f"- {k}: {v}" for k, v in sorted(stats.items()))
        print(summary)
        if os.environ.get("GITHUB_STEP_SUMMARY"):
            with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
                f.write(f"## Editorial import {'(dry run)' if args.dry_run else ''}\n\n{summary}\n")
        if args.dry_run:
            conn.rollback()
            print("Dry run: rolled back.")
        else:
            conn.commit()
            print("Committed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
