"""
Monthly data report: how complete and how current Holibase's school holiday data is.

    DATABASE_URL=postgresql://... python scripts/data_report.py [--out report.md] [--today 2026-10-17]

Read-only. Writes Markdown (stdout, or --out) that the workflow posts as a GitHub issue, so the report
arrives by email and the open issue always shows the current state.

Sections
  1. Market readiness for the markets that matter for CoParently and for every country with data:
     ready / next year missing / current year only / outdated / no data.
  2. Regions whose next school year is missing (what to research or wait for), urgent from March on.
  3. Disagreements between sources for the current and next school year (e.g. OpenHolidays vs research).
  4. Unverified calendars waiting for a second source.
  5. Sources that have not delivered for a while.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
from collections import defaultdict

from babel import Locale

# Markets in the order they matter for CoParently. Countries with data are added after these.
PRIORITY = ["DE", "AT", "CH", "NL", "BE", "FR", "LU", "GB", "IE", "US", "CA", "AU", "NZ",
            "ES", "IT", "PT", "PL", "CZ", "SE", "NO", "DK", "FI"]
CALENDAR_YEAR = {"AU", "NZ", "ZA", "BR", "AR", "CL"}  # school year = calendar year
STALE_DAYS = {"openholidays": 14, "python-holidays": 14, "education-gouv-fr": 14, "rijksoverheid-nl": 14}
NAMES = Locale("en").territories


def school_years(today: dt.date) -> tuple[str, str, str, str]:
    """(current, next) for August-start years and (current, next) for calendar-year countries."""
    y = today.year if today.month >= 8 else today.year - 1
    return f"{y}-{(y + 1) % 100:02d}", f"{y + 1}-{(y + 2) % 100:02d}", str(today.year), str(today.year + 1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    ap.add_argument("--today")
    args = ap.parse_args()
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("DATABASE_URL is not set")
        return 2
    import psycopg

    today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()
    cur_sy, next_sy, cur_cy, next_cy = school_years(today)
    urgent = today.month in (3, 4, 5, 6, 7)  # parents plan the summer and the next school year
    out: list[str] = []

    with psycopg.connect(dsn) as conn:
        conn.read_only = True
        cur = conn.cursor()
        # every scope with a visible, confirmed calendar, and its school years
        cur.execute("""
            select c.country_code::text, coalesce(c.authority_id::text, c.subdivision_code, '-') as scope,
                   coalesce(a.name, sd.name, c.subdivision_code, c.country_code::text) as label,
                   array_agg(distinct c.school_year) as years,
                   array_agg(distinct c.source_id) as sources, c.subdivision_code, c.authority_id is not null
              from public.school_calendars c
              left join public.education_authorities a on a.id = c.authority_id
              left join public.subdivisions sd on sd.code = c.subdivision_code
             where c.status = 'confirmed' and public.calendar_visible(c.id)
             group by 1, 2, 3, 6, 7""")
        rows_ = cur.fetchall()
        # a region split into local authorities is covered by them; its region-wide calendar is only a fallback
        split = {(cc, sub) for cc, _, _, _, _, sub, is_auth in rows_ if is_auth and sub}
        scopes = defaultdict(list)
        for cc, scope, label, years, sources, sub, is_auth in rows_:
            if not is_auth and (cc, sub) in split:
                continue
            scopes[cc].append(dict(scope=scope, label="nationwide" if scope == "-" else label, years=set(years), sources=set(sources)))

        # 1. market readiness
        rows, gaps = [], defaultdict(list)
        for cc in PRIORITY + sorted(set(scopes) - set(PRIORITY)):
            items = scopes.get(cc, [])
            cy = cc in CALENDAR_YEAR or any(len(y) == 4 for s in items for y in s["years"])
            c_lbl, n_lbl = (cur_cy, next_cy) if cy else (cur_sy, next_sy)
            n = len(items)
            has_cur = sum(c_lbl in s["years"] for s in items)
            has_next = sum(n_lbl in s["years"] for s in items)
            if not n:
                status = "⚪ no data"
            elif has_cur >= 0.9 * n and has_next >= 0.9 * n:
                status = "🟢 ready"
            elif has_cur >= 0.9 * n:
                status = "🟡 next year missing"
            elif has_cur:
                status = "🟠 partly current"
            else:
                status = "🔴 outdated"
            if cc in PRIORITY or n:
                rows.append(f"| {NAMES.get(cc, cc)} ({cc}){' ★' if cc in PRIORITY else ''} | {status} | {n} | "
                            f"{has_cur}/{n} | {has_next}/{n} | "
                            f"{', '.join(sorted({src for s in items for src in s['sources']})) or '–'} |")
            if n and has_cur:  # only countries that are alive: list what is missing for next year
                for s in items:
                    if n_lbl not in s["years"]:
                        gaps[cc].append(s["label"])

        n_ready = sum("🟢" in r for r in rows)
        out += [f"# Holibase data report, {today:%d %b %Y}", "",
                f"School years checked: **{cur_sy}** (current) and **{next_sy}** (next); "
                f"calendar-year countries {cur_cy} and {next_cy}. {n_ready} countries ready.", "",
                "★ = priority market for CoParently. Ready = at least 90 % of regions have the current and the next school year.", "",
                "## 1. Market readiness", "",
                "| Country | Status | Regions | Current year | Next year | Sources |", "|---|---|---|---|---|---|", *rows, ""]

        # 2. gaps
        out += ["## 2. Next school year missing" + (" ⚠️ urgent: parents plan the summer now" if urgent else ""), ""]
        if not gaps:
            out.append("Nothing missing.")
        for cc in sorted(gaps, key=lambda c: (c not in PRIORITY, PRIORITY.index(c) if c in PRIORITY else 0, c)):
            labels = sorted(gaps[cc])
            shown = ", ".join(labels[:25]) + (f" and {len(labels) - 25} more" if len(labels) > 25 else "")
            out.append(f"- **{NAMES.get(cc, cc)}** ({len(labels)}): {shown}")
        out.append("")

        # 3. disagreements between sources (any lower-ranked calendar vs the visible one)
        cur.execute("""
            with pairs as (
              select v.country_code::text cc, coalesce(v.authority_id::text, v.subdivision_code, '-') scope,
                     coalesce(v.subdivision_code, v.country_code::text) label, v.school_year sy,
                     v.id vid, v.source_id vsrc, o.id oid, o.source_id osrc
                from public.school_calendars v
                join public.school_calendars o
                  on o.id <> v.id and o.status = 'confirmed' and o.country_code = v.country_code
                 and o.subdivision_code is not distinct from v.subdivision_code
                 and o.authority_id is not distinct from v.authority_id and o.school_year = v.school_year
               where v.status = 'confirmed' and public.calendar_visible(v.id) and v.school_year = any(%s))
            select p.cc, p.label, p.sy, p.vsrc, p.osrc, q.label, q.start_date, q.end_date,
                   (select string_agg(r.start_date || '–' || r.end_date, ', ' order by r.start_date)
                      from public.school_calendar_periods r
                     where r.calendar_id = p.vid and r.kind = 'break'
                       and r.start_date <= q.end_date + 10 and r.end_date >= q.start_date - 10) shown
              from pairs p join public.school_calendar_periods q on q.calendar_id = p.oid and q.kind = 'break'
             where not exists (select 1 from public.school_calendar_periods r where r.calendar_id = p.vid
                                  and r.start_date = q.start_date and r.end_date = q.end_date)
               -- ignore a break that only differs by the weekend around it
               and not exists (select 1 from public.school_calendar_periods r where r.calendar_id = p.vid
                                  and abs(r.start_date - q.start_date) <= 2 and abs(r.end_date - q.end_date) <= 2)
             order by 1, 2, 3, 7""", ([cur_sy, next_sy, cur_cy, next_cy],))
        diffs = cur.fetchall()
        out += ["## 3. Sources disagree", "",
                "The API shows the first source; the second has other dates. Worth a look where it matters.", ""]
        if not diffs:
            out.append("No disagreements beyond a weekend.")
        else:
            out += ["| Region | Year | Shown (source) | Other source | Break | Other dates |", "|---|---|---|---|---|---|"]
            for cc, label, sy, vsrc, osrc, blabel, s, e, shown in diffs[:80]:
                out.append(f"| {label} | {sy} | {shown or 'missing'} ({vsrc}) | {osrc} | {blabel} | {s}–{e} |")
            if len(diffs) > 80:
                out.append(f"\n…and {len(diffs) - 80} more.")
        out.append("")

        # 4. unverified
        cur.execute("""select country_code::text, count(*) from public.school_calendars
                        where status = 'pending' and school_year = any(%s) group by 1 order by 2 desc""",
                    ([cur_sy, next_sy, cur_cy, next_cy],))
        pending = cur.fetchall()
        out += ["## 4. Unverified calendars (current and next year)", ""]
        out.append(", ".join(f"{NAMES.get(cc, cc)}: {n}" for cc, n in pending) if pending else "None.")
        out.append("")

        # 5. source freshness
        cur.execute("""select source_id, max(source_retrieved_at), count(*) filter (where status = 'confirmed')
                         from public.school_calendars where source_retrieved_at is not null group by 1 order by 1""")
        out += ["## 5. Sources", "", "| Source | Last delivered | Calendars | |", "|---|---|---|---|"]
        for src, last, n in cur.fetchall():
            age = (dt.datetime.now(dt.timezone.utc) - last).days if last else None
            limit = STALE_DAYS.get(src)
            flag = "⚠️ overdue" if limit and age is not None and age > limit else ""
            out.append(f"| {src} | {last:%d %b %Y} ({age} days ago) | {n} | {flag} |")
        out.append("")

    text = "\n".join(out) + "\n"
    if args.out:
        with open(args.out, "w") as f:
            f.write(text)
    print(text)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
            f.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
