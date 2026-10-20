"""
Check the school calendars sent with the form on holibase.org and publish the good ones.

    DATABASE_URL=postgresql://... python scripts/process_submissions.py [--dry-run] [--limit 200]

For every submission with status 'received' (see migration 20261020120000_submission_form.sql):

  1. The dates must be plausible (scripts/auto_research.py check(): inside the school year, at least two
     breaks, a break around Christmas in Europe, no overlapping breaks)             otherwise: rejected
  2. If they agree with the calendar the API already shows (weekend shifts ignored),
     that calendar gets one more confirmation                                       -> duplicate
  3. The linked document is fetched and every date looked for in it (same parser as the automatic research).
     All dates found and the link is on an official domain                         -> community calendar,
                                                                                       confirmed (accepted)
     otherwise                                                                     -> community calendar,
                                                                                       pending (needs_review)
     A confirmed submission that contradicts an official or researched calendar stays hidden behind it
     (they rank higher) and is listed for review in the monthly data report; one that corrects library
     data (python-holidays, OpenHolidays) replaces it at once.

No language model is involved; it runs every night before the website is rebuilt.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import auto_research as ar  # noqa: E402  (shared fetching, date parsing and checks)

NS = uuid.UUID("7e2b9c41-5a3d-4f8e-b1c6-2d9e0f4a7b58")  # community calendars


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=200)
    args = ap.parse_args()
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("DATABASE_URL is not set")
        return 2
    import psycopg
    from psycopg.types.json import Jsonb

    conf = json.load(open(ar.SOURCES, encoding="utf-8"))["countries"]
    stats = Counter()
    lines: list[str] = []

    with psycopg.connect(dsn) as conn:
        cur = conn.cursor()
        cur.execute("""select id::text, country_code::text, subdivision_code, authority_id::text, authority_name, school_year,
                              source_url, extracted
                         from public.submissions where status = 'received' order by created_at limit %s""", (args.limit,))
        rows = cur.fetchall()
        for sid, cc, sub, auth, auth_name, sy, url, ex in rows:
            label = f"{cc} {auth_name or sub or 'nationwide'} {sy}"
            ex = ex or {}
            cfg = conf.get(cc, {})
            lang = (ex.get("lang") or cfg.get("lang") or "en")[:2]
            cal = {"school_year": sy, "first_day": ex.get("first_day"), "last_day": ex.get("last_day"),
                   "periods": [{"kind": p.get("kind") or "break", "start_date": p.get("start_date"), "end_date": p.get("end_date"),
                                "name_local": p.get("name") or "", "name_en": p.get("name") or ""} for p in ex.get("periods") or []]}

            def done(status: str, reason: str | None = None, calendar_id: str | None = None) -> None:
                stats[status] += 1
                lines.append(f"- {label}: **{status}**{f' – {reason}' if reason else ''}")
                cur.execute("""update public.submissions set status = %s, rejection_reason = %s, calendar_id = %s,
                                      processed_at = now() where id = %s""", (status, reason, calendar_id, sid))

            try:
                with conn.transaction():  # a savepoint: one bad submission must not undo the others
                    periods, errors = ar.check(cal, cc)
                    if errors:
                        done("rejected", "; ".join(errors[:3]))
                        continue
                    ours = [(p["start"], p["end"]) for p in periods if p["kind"] == "break"]

                    # what the API shows today for this scope and year
                    cur.execute("""select c.id::text, c.origin, c.source_id,
                                          array_agg(array[p.start_date, p.end_date]) filter (where p.kind = 'break')
                                     from public.school_calendars c
                                     left join public.school_calendar_periods p on p.calendar_id = c.id
                                    where c.country_code = %s and c.subdivision_code is not distinct from %s
                                      and c.authority_id is not distinct from %s and c.school_year = %s
                                      and c.status = 'confirmed' and public.calendar_visible(c.id)
                                    group by 1, 2, 3""", (cc, sub, auth, sy))
                    shown = cur.fetchall()
                    verdicts = [(cid, origin, src, ar.compare(ours, [(a, b) for a, b in (br or [])])) for cid, origin, src, br in shown]
                    if verdicts and all(v[3] == "agree" for v in verdicts):
                        cur.execute("update public.school_calendars set confirmations = confirmations + 1 where id = any(%s::uuid[])",
                                    ([v[0] for v in verdicts],))
                        done("duplicate", "matches the calendar already shown", verdicts[0][0])
                        continue

                    # look for every date in the linked document
                    log: list[str] = []
                    parts = ar.fetch_document(url, [sy], log)
                    text = "\n".join(t for _, t in parts)
                    ok, total = ar.verified(cal, periods, ar.date_mentions(text)) if text else (0, 0)
                    official = ar.is_official(url, cfg.get("official", []) + ar.EXTRA_OFFICIAL.get(cc, []))
                    full = bool(text) and ok == total
                    status = "confirmed" if full and official else "pending"
                    why = ("all dates found in the official document" if status == "confirmed" else
                           "the document could not be read" if not text else
                           f"{total - ok} of {total} dates not found in the document" if not full else
                           "the link is not on an official domain")

                    cid = str(uuid.uuid5(NS, f"{cc}|{sub or ''}|{auth or ''}|{sy}|{url}"))
                    cur.execute("""
                        insert into public.school_calendars (id, country_code, subdivision_code, authority_id, school_year, title,
                               origin, status, source_id, source_version, source_url, source_retrieved_at, first_day, last_day, notes)
                        values (%s, %s, %s, %s, %s, %s, 'community', %s, 'community', %s, %s, now(), %s, %s, %s)
                        on conflict on constraint school_calendars_natural_key do update set
                               status = excluded.status, source_version = excluded.source_version,
                               source_retrieved_at = excluded.source_retrieved_at, first_day = excluded.first_day,
                               last_day = excluded.last_day, notes = excluded.notes
                        returning id::text""",
                                (cid, cc, sub, auth, sy, auth_name, status, f"submission:{sid}", url,
                                 ar.d(cal["first_day"]), ar.d(cal["last_day"]),
                                 f"Submitted with the form on holibase.org; {ok} of {total} dates found in the linked document; {why}."))
                    cid = cur.fetchone()[0]
                    cur.execute("delete from public.school_calendar_periods where calendar_id = %s", (cid,))
                    cur.executemany("""insert into public.school_calendar_periods (calendar_id, start_date, end_date, kind, label, names)
                                       values (%s, %s, %s, %s, %s, %s)
                                       on conflict on constraint school_calendar_periods_natural_key do nothing""",
                                    [(cid, p["start"], p["end"], p["kind"], (p.get("name_local") or p["kind"])[:200],
                                      Jsonb({lang: p["name_local"]} if p.get("name_local") else {})) for p in periods])

                    higher = [v for v in verdicts if v[3] == "disagree" and v[1] in ("official", "editorial")]
                    if status == "confirmed" and not higher:
                        done("accepted", why, cid)
                    else:
                        done("needs_review", why if not higher else f"{why}; differs from the {higher[0][2]} calendar", cid)
            except Exception as e:  # noqa: BLE001 - one bad submission must not stop the others
                done("failed", f"{type(e).__name__}: {e}"[:300])

        summary = (f"## Submissions {'(dry run)' if args.dry_run else ''}\n\n{len(rows)} new: "
                   + ", ".join(f"{k} {v}" for k, v in sorted(stats.items())) + "\n\n" + "\n".join(lines) + "\n")
        print(summary)
        if os.environ.get("GITHUB_STEP_SUMMARY"):
            with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
                f.write(summary)
        if args.dry_run:
            conn.rollback()
        else:
            conn.commit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
