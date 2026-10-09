"""
Import editorial school calendars (data/editorial/*.json) into the database.

    DATABASE_URL=postgresql://... python scripts/import_editorial.py [--dry-run] [files...]

Each file holds {"dataset", "retrieved", "method", "calendars": [...]}. Every calendar is upserted by its
id (deterministic UUID), its periods are replaced by exactly the periods in the file, and the education
authority it belongs to is created if missing. Re-running is safe; calendars not in the files are untouched.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from collections import Counter

import psycopg
from psycopg.types.json import Jsonb

SOURCE_ID = "editorial"


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

    stats = Counter()
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        for path in files:
            data = json.load(open(path, encoding="utf-8"))
            for c in data["calendars"]:
                auth_id = c.get("authority_id")
                if auth_id:
                    cur.execute(
                        """insert into public.education_authorities (id, country_code, subdivision_code, kind, name, external_ids, source_id)
                           values (%s, %s, %s, %s, %s, %s, %s)
                           on conflict (id) do update set name = excluded.name,
                                 -- once the NCES import set the real id, the research claim is no longer merged back in
                                 external_ids = public.education_authorities.external_ids
                                   || case when public.education_authorities.external_ids ? 'nces_leaid'
                                           then excluded.external_ids - 'nces_leaid_claimed' else excluded.external_ids end
                           returning (xmax = 0)""",
                        (auth_id, c["country_code"], c["subdivision_code"], c["authority_kind"] or "other",
                         c["authority"], Jsonb(c.get("authority_ext") or {}), SOURCE_ID),
                    )
                    stats["authorities_new" if cur.fetchone()[0] else "authorities_existing"] += 1

                cur.execute(
                    """insert into public.school_calendars
                         (id, country_code, subdivision_code, authority_id, school_year, title, origin, status,
                          source_id, source_version, source_url, source_retrieved_at, first_day, last_day, notes)
                       values (%(id)s, %(country_code)s, %(subdivision_code)s, %(authority_id)s, %(school_year)s, %(title)s,
                               'editorial', %(status)s, %(src)s, %(dataset)s, %(source_url)s, %(retrieved)s,
                               %(first_day)s, %(last_day)s, %(notes)s)
                       on conflict (id) do update set
                         -- calendars superseded by an official source stay superseded
                         status = case when public.school_calendars.status = 'outdated'
                                            and public.school_calendars.notes like '%%Superseded by official data%%'
                                       then 'outdated' else excluded.status end, source_url = excluded.source_url, source_version = excluded.source_version,
                         source_retrieved_at = excluded.source_retrieved_at, first_day = excluded.first_day,
                         last_day = excluded.last_day, title = excluded.title,
                         notes = case when public.school_calendars.notes like '%%Superseded by official data%%'
                                      then public.school_calendars.notes else excluded.notes end
                       returning (xmax = 0)""",
                    dict(c, title=c.get("authority"), src=SOURCE_ID, dataset=data["dataset"], retrieved=data["retrieved"]),
                )
                stats["calendars_new" if cur.fetchone()[0] else "calendars_updated"] += 1
                stats[f"calendars_{c['status']}"] += 1

                cur.execute("delete from public.school_calendar_periods where calendar_id = %s", (c["id"],))
                stats["periods_replaced"] += cur.rowcount
                for p in c["periods"]:
                    cur.execute(
                        """insert into public.school_calendar_periods (calendar_id, start_date, end_date, kind, label, names)
                           values (%s, %s, %s, %s, %s, %s) on conflict on constraint school_calendar_periods_natural_key
                           do update set kind = excluded.kind, names = excluded.names""",
                        (c["id"], p["start_date"], p["end_date"], p["kind"], p["label"], Jsonb(p["names"])),
                    )
                    stats["periods_written"] += 1

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
