"""
Turn deep-research results for US districts into an editorial import file.

    python scripts/research_to_editorial.py data/research/us-2026-10

Reads   <dir>/districts.csv            the batch list (holibase_id, nces_leaid, name, state, ...)
        <dir>/results/*.csv            research output, one file per batch and model, e.g. batch-01-gpt.csv
Writes  data/editorial/<dir name>.json  picked up by the editorial import workflow on push
        <dir>/REPORT.md                what was accepted, what is pending and why, what was rejected

A calendar is 'confirmed' only when all of these hold, otherwise it is 'pending' (served with include=pending):
  * board_status = approved and an official source URL (no aggregator sites)
  * first and last day of school, at least 6 periods, Thanksgiving Day off and a winter break around Christmas
  * if two models researched the same district and year, their breaks agree
"""
from __future__ import annotations

import csv
import datetime as dt
import glob
import json
import os
import re
import sys
import uuid
from collections import Counter, defaultdict

NS = uuid.UUID("2b0b6f3e-7c41-4e0b-9a3c-5d7f1e2a9c44")  # same namespace as the first research import
KINDS = {"break", "holiday", "teacher_day", "early_release", "other"}
DROP = re.compile(r"make ?up|weather|inclement|contingency|possible|e-?learning day|exam", re.I)
AGGREGATORS = re.compile(r"publicholidays|schoolcalendarinfo|officeholidays|calendarlabs|kidscalendar|schoolholidays|"
                         r"timeanddate|calendar-12|wincalendar|holidays-?calendar|schoolcalendar\.(org|net)|"
                         r"patch\.com|wikipedia", re.I)
MODEL_RANK = {"gpt": 0, "chatgpt": 0, "claude": 1, "gemini": 2}


def parse_date(s: str) -> dt.date | None:
    s = (s or "").strip()
    try:
        return dt.date.fromisoformat(s)
    except ValueError:
        return None


def year_window(sy: str) -> tuple[dt.date, dt.date] | None:
    m = re.fullmatch(r"(\d{4})-(\d{2})", sy.strip())
    if not m:
        return None
    y = int(m.group(1))
    return dt.date(y, 7, 1), dt.date(y + 1, 8, 31)


def thanksgiving(year: int) -> dt.date:
    d = dt.date(year, 11, 1)
    return d + dt.timedelta(days=(3 - d.weekday()) % 7 + 21)


def covers(periods: list[dict], day: dt.date) -> bool:
    return any(dt.date.fromisoformat(p["start_date"]) <= day <= dt.date.fromisoformat(p["end_date"])
               for p in periods if p["kind"] != "early_release")


def main(folder: str) -> int:
    folder = folder.rstrip("/")
    districts = {r["nces_leaid"]: r for r in csv.DictReader(open(os.path.join(folder, "districts.csv")))}
    report = Counter()
    rejected: list[str] = []
    # (leaid, year) -> model -> {"cal": row, "periods": [...]}
    found: dict[tuple[str, str], dict[str, dict]] = defaultdict(dict)

    for path in sorted(glob.glob(os.path.join(folder, "results", "*.csv"))):
        model = os.path.basename(path)[:-4].split("-")[-1].lower()
        text = open(path, encoding="utf-8-sig").read()
        text = re.sub(r"^```\w*\s*|\s*```\s*$", "", text.strip())  # tolerate fenced output
        for n, r in enumerate(csv.DictReader(text.splitlines()), start=2):
            r = {k.strip().lower(): (v or "").strip() for k, v in r.items() if k}
            leaid = r.get("nces_leaid", "").zfill(7)
            where = f"{os.path.basename(path)}:{n}"
            if leaid not in districts:
                rejected.append(f"{where}: unknown nces_leaid {r.get('nces_leaid')}")
                continue
            sy = r.get("school_year", "")
            win = year_window(sy)
            if not win:
                rejected.append(f"{where}: bad school_year {sy!r}")
                continue
            slot = found[(leaid, sy)].setdefault(model, {"cal": None, "periods": [], "file": os.path.basename(path)})
            if r.get("row_type") == "calendar":
                slot["cal"] = r
                continue
            if r.get("row_type") != "period":
                rejected.append(f"{where}: bad row_type {r.get('row_type')!r}")
                continue
            kind, label = r.get("kind", "").lower(), r.get("label", "")
            s, e = parse_date(r.get("start_date")), parse_date(r.get("end_date")) or parse_date(r.get("start_date"))
            if kind not in KINDS or not label or not s or not e:
                rejected.append(f"{where}: incomplete period {kind!r} {label!r} {r.get('start_date')}..{r.get('end_date')}")
                continue
            if DROP.search(label):
                report["dropped_makeup_or_contingency"] += 1
                continue
            if e < s or not (win[0] <= s <= win[1]) or (e - s).days > 120:
                rejected.append(f"{where}: implausible dates {label} {s}..{e} for {sy}")
                continue
            slot["periods"].append(dict(start_date=s.isoformat(), end_date=e.isoformat(), kind=kind, label=label,
                                        names={"en": label}))

    calendars, pending_reasons, not_found = [], [], []
    for (leaid, sy), by_model in sorted(found.items()):
        d = districts[leaid]
        models = sorted(by_model, key=lambda m: MODEL_RANK.get(m, 9))
        main_model = next((m for m in models if by_model[m]["periods"]), models[0])
        best = by_model[main_model]
        cal = best["cal"] or {}
        if (cal.get("board_status") or "").lower() == "not_found" and not best["periods"]:
            not_found.append(f"{d['nces_name'] or d['name']} ({d['state']}) {sy}: {cal.get('notes', '')}")
            continue
        if not best["periods"]:
            continue
        periods = sorted({(p["start_date"], p["end_date"], p["label"]): p for p in best["periods"]}.values(),
                         key=lambda p: (p["start_date"], p["label"]))
        reasons = []
        status_board = (cal.get("board_status") or "").lower()
        src = cal.get("source_url", "")
        if status_board != "approved":
            reasons.append(f"board status {status_board or 'unknown'}")
        if not src.startswith("http"):
            reasons.append("no source URL")
        elif AGGREGATORS.search(src):
            reasons.append("source is an aggregator site")
        first, last = parse_date(cal.get("start_date")), parse_date(cal.get("end_date"))
        if not first or not last:
            reasons.append("first or last day missing")
        if len(periods) < 6:
            reasons.append(f"only {len(periods)} periods")
        y = int(sy[:4])
        if not covers(periods, thanksgiving(y)):
            reasons.append("Thanksgiving not off")
        if not any(p["kind"] == "break" and p["start_date"] <= f"{y + 1}-01-01" and p["end_date"] >= f"{y}-12-22"
                   for p in periods):
            reasons.append("no winter break around Christmas")
        others = [m for m in models if m != main_model and by_model[m]["periods"]]
        disagreements = []
        for m in others:
            # a conflict = both models describe the same break (overlapping dates) differently;
            # breaks one model simply did not report are not conflicts
            a = [(p["start_date"], p["end_date"], p["label"]) for p in periods if p["kind"] == "break"]
            b = [(p["start_date"], p["end_date"]) for p in by_model[m]["periods"] if p["kind"] == "break"]
            for bs, be in b:
                for as_, ae, al in a:
                    if as_ <= be and bs <= ae and (as_, ae) != (bs, be):
                        disagreements.append(f"{al}: {main_model} {as_}..{ae}, {m} {bs}..{be}")
        if disagreements:
            reasons += disagreements
        status = "pending" if reasons else "confirmed"
        if reasons:
            pending_reasons.append(f"{d['nces_name'] or d['name']} ({d['state']}) {sy}: {'; '.join(reasons)}")
        sub = f"US-{d['state']}"
        editorial_auth = str(uuid.uuid5(NS, f"auth|US|{sub}|{d['name']}")) == d["holibase_id"]
        cid = (uuid.uuid5(NS, f"cal|US|{sub}|{d['name']}|{sy}") if editorial_auth
               else uuid.uuid5(NS, f"cal|US|auth:{d['holibase_id']}|{sy}"))
        ext = {k: v for k, v in {
            "calendar_feed_url": cal.get("feed_url") if (cal.get("feed_url") or "").startswith(("http", "webcal")) else None,
            "calendar_feed_format": cal.get("feed_format") or None,
            "website": cal.get("website") if (cal.get("website") or "").startswith("http") else None,
        }.items() if v}
        note_bits = [f"Researched by {', '.join(models)} (Holibase deep research, Oct 2026)."]
        if status == "confirmed" and others:
            note_bits.append("Breaks identical across models.")
        if cal.get("notes"):
            note_bits.append(cal["notes"])
        calendars.append(dict(
            id=str(cid), country_code="US", subdivision_code=sub, authority=d["name"], authority_id=d["holibase_id"],
            authority_kind="school_district", authority_ext=ext, school_year=sy, status=status,
            source_url=src or None, first_day=first.isoformat() if first else None,
            last_day=last.isoformat() if last else None, notes=" ".join(note_bits), periods=periods))
        report[f"calendars_{status}"] += 1
        if ext.get("calendar_feed_url"):
            report["with_feed_url"] += 1

    name = os.path.basename(folder)
    out = os.path.join(os.path.dirname(__file__), "..", "data", "editorial", f"{name}.json")
    json.dump(dict(dataset=f"{name}", retrieved=dt.date.today().isoformat(),
                   method="Deep research per district from official district sources, validated by scripts/research_to_editorial.py",
                   calendars=calendars), open(out, "w"), ensure_ascii=False, indent=1)
    lines = [f"# Research import {name}", "", *[f"- {k}: {v}" for k, v in sorted(report.items())],
             f"- not_found: {len(not_found)}", f"- rejected_rows: {len(rejected)}", "",
             "## Pending (served only with include=pending)", "", *[f"- {x}" for x in pending_reasons], "",
             "## Not found", "", *[f"- {x}" for x in not_found], "",
             "## Rejected rows", "", *[f"- {x}" for x in rejected], ""]
    open(os.path.join(folder, "REPORT.md"), "w").write("\n".join(lines))
    print("\n".join(lines[:8]))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "data/research/us-2026-10"))
