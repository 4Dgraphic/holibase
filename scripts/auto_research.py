"""
Automatic research for missing school calendars.

    DATABASE_URL=... OPENAI_API_KEY=... python scripts/auto_research.py [--countries ES,IT] [--max-calls 30]
        [--max-searches 10] [--no-discover] [--out data/editorial/auto-2026-11-02.json] [--report report.md]

Finds every region whose current or next school year has no confirmed calendar (the gaps in the monthly
data report), reads the official page or PDF that publishes its holidays and has a language model copy the
dates out. Nothing is written to the database here: the result is an editorial file that the workflow
imports with scripts/import_editorial.py and commits, so every change is in the git history.

Model: OpenAI if OPENAI_API_KEY is set (OPENAI_MODEL, default gpt-5-mini), otherwise Anthropic with
ANTHROPIC_API_KEY (ANTHROPIC_MODEL). The model only reads; fetching and every check run here.

Where the documents come from (data/research/sources.json)
  * sources listed per country, and
  * discovery: the model searches the web for the official page; only URLs on the country's official
    domains are used, everything else is listed in the report as a candidate. Discovered URLs that
    deliver a calendar are saved back to sources.json, so the next run goes there directly.

A calendar is
  * rejected  when its dates are implausible: outside the school year, overlapping breaks, no break
              around Christmas (Europe), fewer than two breaks, or neither a summer break nor first/last day;
  * pending   (served only with include=pending, listed in the data report) when it contradicts another
              source, or when it is not on an official domain and no second source agrees;
  * confirmed when it comes from an official domain and every date was found printed in the document
              (so the model cannot have invented it), or when a second source agrees with it.
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import html.parser
import io
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections import Counter, defaultdict

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SOURCES = os.path.join(ROOT, "data", "research", "sources.json")
NS = uuid.UUID("c3f1a6d2-8e4b-4f7a-9b2c-1d5e7a9f0b36")  # automatic research calendars
UA = "holibase-research/1.0 (+https://holibase.org; hello@holibase.org)"
MAX_CHARS = 90_000
MAX_BYTES = 15_000_000
PRIORITY = ["DE", "AT", "CH", "NL", "BE", "FR", "LU", "GB", "IE", "US", "CA", "AU", "NZ",
            "ES", "IT", "PT", "PL", "CZ", "SE", "NO", "DK", "FI"]
CALENDAR_YEAR = {"AU", "NZ", "ZA", "BR", "AR", "CL"}
EUROPE = set("AD AL AT BA BE BG BY CH CY CZ DE DK EE ES FI FR GB GR HR HU IE IS IT LI LT LU LV MC MD ME MK MT "
             "NL NO PL PT RO RS SE SI SK SM UA VA XK".split())
AGGREGATORS = re.compile(r"publicholidays|schoolholidays|schulferien\.org|ferienwiki|officeholidays|timeanddate|"
                         r"calendarlabs|wikipedia|tuttitalia|money\.it|micole|loentiendo|calendarr|kalender|"
                         r"feriados|vacances-scolaires\.(?:education|net)|schoolvakanties-nederland", re.I)
GENERIC_OFFICIAL = r"(^|\.)(gov|gob|gouv|govt|gv|government|regierung)\.[a-z]{2,3}$"
KINDS = {"break", "holiday", "teacher_day", "other"}
LANGS = ["en", "de", "fr", "it", "es", "pt", "nl", "pl", "ro", "ca", "gl", "eu", "hr", "hu", "cs", "sk", "sl",
         "lv", "lt", "et", "sv", "da", "nb", "fi", "sr", "sq", "mt", "lb", "rm", "el", "bg", "uk"]


# ---------------------------------------------------------------- text and dates

def fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"[‐-―−]", "-", s).replace(" ", " ")


def _month_tokens() -> dict[str, int]:
    from babel import Locale
    out: dict[str, int] = {}
    for lang in LANGS:
        try:
            loc = Locale.parse(lang)
        except Exception:  # noqa: BLE001 - a locale babel does not know is simply skipped
            continue
        for ctx in ("format", "stand-alone"):
            for width in ("wide", "abbreviated"):
                for m, name in loc.months[ctx][width].items():
                    t = fold(name).strip(".")
                    if len(t) >= 3 and not t.isdigit():
                        out.setdefault(t, m)
    for t, m in {"sept": 9, "sep": 9, "febr": 2, "aug": 8}.items():
        out.setdefault(t, m)
    return out


MONTHS = _month_tokens()
_MN = "|".join(sorted(map(re.escape, MONTHS), key=len, reverse=True))
RX = [
    ("dm", re.compile(r"(?<!\d)(\d{1,2})\s*[./]\s*(\d{1,2})(?:\s*[./]\s*(?:\d{4}|\d{2}))?(?![\d/])")),
    ("iso", re.compile(r"(\d{4})-(\d{2})-(\d{2})")),
    ("range_dm", re.compile(r"(?<!\d)(\d{1,2})\.?\s*(?:-|al|au|bis|do|to|a|tot|t/m|till|until|i|et|y|e)\s*"
                            r"(\d{1,2})\s*[./]\s*(\d{1,2})(?!\d)")),
    ("range_dname", re.compile(r"(?<!\d)(\d{1,2})(?:\.|º|o|er|st|nd|rd|th)?\s*(?:-|al|au|bis|do|to|a|tot|t/m|till|"
                               r"until|i|et|y|e)\s*(\d{1,2})(?:\.|º|o|er|st|nd|rd|th)?\s*(?:de\s+|d')?(" + _MN + r")\b")),
    ("dname", re.compile(r"(?<!\d)(\d{1,2})(?:\.|º|o|er|st|nd|rd|th)?\s*(?:de\s+|d')?(" + _MN + r")\b")),
    ("named_range", re.compile(r"\b(" + _MN + r")\.?\s+(\d{1,2})\.?\s*-\s*(\d{1,2})(?!\d)")),
    ("named", re.compile(r"\b(" + _MN + r")\.?\s+(\d{1,2})(?!\d)")),
]


def date_mentions(text: str) -> set[tuple[int, int]]:
    """Every (day, month) printed in the text, in any of the usual European notations."""
    t = fold(text)
    found: set[tuple[int, int]] = set()

    def add(d, m):
        d, m = int(d), int(m)
        if 1 <= d <= 31 and 1 <= m <= 12:
            found.add((d, m))

    for kind, rx in RX:
        for g in rx.findall(t):
            if kind == "dm":
                add(g[0], g[1])
            elif kind == "iso":
                add(g[2], g[1])
            elif kind == "range_dm":
                add(g[0], g[2]); add(g[1], g[2])
            elif kind == "range_dname":
                add(g[0], MONTHS[g[2]]); add(g[1], MONTHS[g[2]])
            elif kind == "dname":
                add(g[0], MONTHS[g[1]])
            elif kind == "named_range":
                add(g[1], MONTHS[g[0]]); add(g[2], MONTHS[g[0]])
            elif kind == "named":
                add(g[1], MONTHS[g[0]])
    return found


class _Text(html.parser.HTMLParser):
    BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "table", "section", "article",
             "ul", "ol", "dd", "dt", "header", "footer"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.links: list[tuple[str, str]] = []
        self.skip = 0
        self._href: str | None = None
        self._atext: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "svg", "template"):
            self.skip += 1
        elif tag in self.BLOCK:
            self.out.append("\n")
        elif tag in ("td", "th"):
            self.out.append(" | ")
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._atext = []

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg", "template"):
            self.skip = max(0, self.skip - 1)
        elif tag in self.BLOCK:
            self.out.append("\n")
        if tag == "a" and self._href:
            self.links.append((self._href, " ".join(self._atext)))
            self._href = None

    def handle_data(self, data):
        if not self.skip:
            self.out.append(data)
            if self._href is not None:
                self._atext.append(data)


def html_to_text(raw: str) -> tuple[str, list[tuple[str, str]]]:
    p = _Text()
    p.feed(raw)
    text = "".join(p.out)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\s*\n\s*", "\n", text)
    return text.strip(), p.links


def pdf_to_text(raw: bytes) -> str:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(raw))
    return "\n".join((page.extract_text() or "") for page in reader.pages[:60])


def shorten(text: str, limit: int = MAX_CHARS) -> str:
    """Keep the parts of a long document that carry dates."""
    if len(text) <= limit:
        return text
    lines = text.split("\n")
    keep = set()
    for i, line in enumerate(lines):
        if date_mentions(line):
            keep.update(range(max(0, i - 3), min(len(lines), i + 4)))
    out = "\n".join(lines[i] for i in sorted(keep))
    return out[:limit]


# ---------------------------------------------------------------- fetching

def host(url: str) -> str:
    return (urllib.parse.urlsplit(url).hostname or "").lower().removeprefix("www.")


def is_official(url: str, patterns: list[str]) -> bool:
    h = host(url)
    if not h or AGGREGATORS.search(url):
        return False
    return any(re.search(p, h) for p in patterns + [GENERIC_OFFICIAL])


BROWSER_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/141.0.0.0 Safari/537.36")


def http_get(url: str) -> tuple[bytes, str]:
    """Some government sites refuse unknown clients (HTTP 403); then retry once like a browser."""
    for ua in (UA, BROWSER_UA):
        req = urllib.request.Request(url, headers={
            "User-Agent": ua, "Accept": "text/html,application/xhtml+xml,application/pdf,*/*;q=0.8",
            "Accept-Language": "en,de;q=0.8,fr;q=0.7,*;q=0.5", "Upgrade-Insecure-Requests": "1"})
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                data = r.read(MAX_BYTES + 1)
                if len(data) > MAX_BYTES:
                    raise ValueError("document larger than 15 MB")
                return data, r.headers.get("Content-Type", "")
        except urllib.error.HTTPError as e:
            if e.code not in (401, 403, 406, 429) or ua == BROWSER_UA:
                raise
            time.sleep(2)
    raise RuntimeError("unreachable")


KEYWORDS = re.compile(r"ferien|vacan|vakant|vacaci|ferie|holiday|kalend|calend|schuljahr|anno.?scol|ano.?escol|"
                      r"curso|schooljaar|annee.?scol|structura|rok.?szkol|tanev|skolsk|school.?year|term", re.I)


def fetch_document(url: str, years: list[str], log: list[str]) -> list[tuple[str, str]]:
    """[(url, text)] for the page and up to three linked PDFs that look like holiday calendars."""
    parts: list[tuple[str, str]] = []
    try:
        raw, ctype = http_get(url)
    except Exception as e:  # noqa: BLE001
        log.append(f"could not fetch {url}: {e}")
        return parts
    if raw[:5] == b"%PDF-" or "pdf" in ctype:
        try:
            parts.append((url, pdf_to_text(raw)))
        except Exception as e:  # noqa: BLE001
            log.append(f"could not read PDF {url}: {e}")
        return parts
    charset = (re.search(r"charset=([\w-]+)", ctype) or [None, "utf-8"])[1]
    text, links = html_to_text(raw.decode(charset, errors="replace"))
    parts.append((url, text))
    digits = {y[:4] for y in years} | {y[-2:] for y in years}
    seen = set()
    for href, label in links:
        full = urllib.parse.urljoin(url, html.unescape(href or ""))
        if full in seen or not full.startswith("http"):
            continue
        blob = f"{full} {label}"
        if (".pdf" in full.lower() or "pdf" in label.lower()) and KEYWORDS.search(blob) \
                and any(d in blob for d in digits) and host(full).split(".")[-2:] == host(url).split(".")[-2:]:
            seen.add(full)
            if len(seen) > 3:
                break
            time.sleep(1)
            try:
                raw2, ctype2 = http_get(full)
                if raw2[:5] == b"%PDF-" or "pdf" in ctype2:
                    parts.append((full, pdf_to_text(raw2)))
            except Exception as e:  # noqa: BLE001
                log.append(f"could not fetch linked {full}: {e}")
    return parts


# ---------------------------------------------------------------- models

PERIOD = {"type": "object", "additionalProperties": False,
          "required": ["kind", "start_date", "end_date", "name_local", "name_en"],
          "properties": {"kind": {"type": "string", "enum": sorted(KINDS)},
                         "start_date": {"type": "string", "description": "YYYY-MM-DD, first day off"},
                         "end_date": {"type": "string", "description": "YYYY-MM-DD, last day off"},
                         "name_local": {"type": "string"}, "name_en": {"type": "string"}}}
CALENDAR = {"type": "object", "additionalProperties": False,
            "required": ["scope", "school_year", "language", "source_url", "first_day", "last_day", "periods"],
            "properties": {"scope": {"type": "string"}, "school_year": {"type": "string"},
                           "language": {"type": "string", "description": "ISO 639-1 code of name_local"},
                           "source_url": {"type": "string"},
                           "first_day": {"type": ["string", "null"]}, "last_day": {"type": ["string", "null"]},
                           "periods": {"type": "array", "items": PERIOD}}}
EXTRACT_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["calendars", "remarks"],
                  "properties": {"calendars": {"type": "array", "items": CALENDAR}, "remarks": {"type": "string"}}}

EXTRACT_SYSTEM = """You copy school holiday dates out of official documents for an open database.
Rules:
- Use only dates printed in the document. Never guess, compute or complete dates, never use your own knowledge.
- Leave out a region or school year the document does not cover. An empty list is a valid answer.
- start_date is the first day without school, end_date the last day without school, exactly as printed.
  If the document prints the last school day before a break and the first school day after it, convert to
  the days off in between.
- kind: break = school holidays of one or more days (autumn, Christmas, winter, Easter, summer, ...);
  holiday = a single public holiday or school day off; teacher_day = a day without classes for teacher
  training; other = anything else without classes. Leave out exams, make-up days and days with classes.
- first_day/last_day: first and last day of classes of the school year if printed, else null.
- Use the scope codes exactly as given. Periods that apply to all requested scopes (e.g. nationwide Christmas,
  Easter and summer holidays) go once into a calendar with scope "ALL"; each scope's own calendar then holds only
  what differs for it (e.g. a winter break that depends on the region). If the dates are the same for every
  scope, return only the "ALL" calendar. If the document distinguishes school types, use primary and lower
  secondary schools.
- name_local in the document's language, name_en a short English name (e.g. "Autumn break").
- source_url: the URL of the document part (see the headers) the dates come from."""

DISCOVER_SYSTEM = """You find official sources of school holiday dates. Search the web and answer with JSON only:
{"sources": [{"scopes": ["<scope code>", ...], "url": "<url>"}]}
Only list pages or PDFs published by the education ministry, the regional government or the education
authority itself (its official bulletin counts). Never list news sites, blogs, school websites or holiday
aggregators. Prefer the page that lists the dates of the requested school years directly. At most 2 URLs per scope."""


class ModelError(RuntimeError):
    pass


def _post(url: str, headers: dict, body: dict, tries: int = 3) -> dict:
    data = json.dumps(body).encode()
    for attempt in range(tries):
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", **headers})
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            raw = e.read().decode(errors="replace")
            try:
                msg = json.loads(raw)["error"]["message"]
            except (ValueError, KeyError, TypeError):
                msg = raw[:300]
            if e.code in (429, 500, 502, 503, 529) and attempt < tries - 1:
                time.sleep(20 * (attempt + 1))
                continue
            raise ModelError(f"HTTP {e.code}: {msg}") from None
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < tries - 1:
                time.sleep(10)
                continue
            raise ModelError(str(e)) from None
    raise ModelError("no response")


def _json_from_text(text: str) -> dict:
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {}


class OpenAIModel:
    provider = "OpenAI"

    def __init__(self, key: str, model: str):
        self.key, self.model = key, model
        self.usage = Counter()
        self._reasoning = model.startswith(("gpt-5", "o3", "o4"))

    def _h(self):
        return {"Authorization": f"Bearer {self.key}"}

    def extract(self, system: str, user: str) -> dict:
        body = {"model": self.model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "response_format": {"type": "json_schema",
                                    "json_schema": {"name": "school_calendars", "strict": True, "schema": EXTRACT_SCHEMA}}}
        if self._reasoning:
            body["reasoning_effort"] = "low"
        try:
            r = _post("https://api.openai.com/v1/chat/completions", self._h(), body)
        except ModelError as e:
            if "reasoning_effort" not in str(e):
                raise
            self._reasoning = False
            body.pop("reasoning_effort")
            r = _post("https://api.openai.com/v1/chat/completions", self._h(), body)
        u = r.get("usage") or {}
        self.usage["input"] += u.get("prompt_tokens", 0)
        self.usage["output"] += u.get("completion_tokens", 0)
        self.usage["calls"] += 1
        msg = r["choices"][0]["message"]
        if msg.get("refusal"):
            raise ModelError(f"refused: {msg['refusal']}")
        return json.loads(msg["content"])

    def search(self, system: str, user: str) -> tuple[dict, list[str]]:
        body = {"model": self.model, "instructions": system, "input": user, "tools": [{"type": "web_search"}]}
        r = _post("https://api.openai.com/v1/responses", self._h(), body)
        u = r.get("usage") or {}
        self.usage["input"] += u.get("input_tokens", 0)
        self.usage["output"] += u.get("output_tokens", 0)
        self.usage["searches"] += 1
        text, cited = "", []
        for item in r.get("output", []):
            for c in item.get("content", []) or []:
                if c.get("type") == "output_text":
                    text += c.get("text", "")
                    cited += [a["url"] for a in c.get("annotations", []) if a.get("type") == "url_citation"]
        return _json_from_text(text), cited


class AnthropicModel:
    provider = "Anthropic"

    def __init__(self, key: str, model: str):
        self.key, self.model = key, model
        self.usage = Counter()

    def _h(self):
        return {"x-api-key": self.key, "anthropic-version": "2023-06-01"}

    def _count(self, r):
        u = r.get("usage") or {}
        self.usage["input"] += u.get("input_tokens", 0)
        self.usage["output"] += u.get("output_tokens", 0)

    def extract(self, system: str, user: str) -> dict:
        body = {"model": self.model, "max_tokens": 16000, "system": system,
                "messages": [{"role": "user", "content": user}],
                "tools": [{"name": "submit", "description": "Submit the calendars", "input_schema": EXTRACT_SCHEMA}],
                "tool_choice": {"type": "tool", "name": "submit"}}
        r = _post("https://api.anthropic.com/v1/messages", self._h(), body)
        self._count(r)
        self.usage["calls"] += 1
        for c in r.get("content", []):
            if c.get("type") == "tool_use":
                return c["input"]
        raise ModelError("no structured answer")

    def search(self, system: str, user: str) -> tuple[dict, list[str]]:
        body = {"model": self.model, "max_tokens": 4000, "system": system,
                "messages": [{"role": "user", "content": user}],
                "tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": 6}]}
        r = _post("https://api.anthropic.com/v1/messages", self._h(), body)
        self._count(r)
        self.usage["searches"] += 1
        text = "".join(c.get("text", "") for c in r.get("content", []) if c.get("type") == "text")
        cited = [x.get("url") for c in r.get("content", []) if c.get("type") == "web_search_tool_result"
                 for x in (c.get("content") or []) if isinstance(x, dict) and x.get("url")]
        return _json_from_text(text), cited


def make_model():
    if os.environ.get("OPENAI_API_KEY"):
        return OpenAIModel(os.environ["OPENAI_API_KEY"], os.environ.get("OPENAI_MODEL") or "gpt-5-mini")
    if os.environ.get("ANTHROPIC_API_KEY"):
        return AnthropicModel(os.environ["ANTHROPIC_API_KEY"], os.environ.get("ANTHROPIC_MODEL") or "claude-haiku-5-5")
    return None


def merge_all(cals: list[dict], codes: set[str]) -> list[dict]:
    """Expand the model's answer: periods given once for "ALL" scopes are added to each scope's own periods.
    A scope without its own calendar only gets the ALL calendar when no scope has one (the document is the
    same everywhere); otherwise its own dates are unknown and it is left out."""
    alls: dict[str, dict] = {}
    own: dict[str, dict[str, dict]] = defaultdict(dict)
    for cal in cals:
        sy = (cal.get("school_year") or "").replace("/", "-").strip()
        if re.fullmatch(r"\d{4}-\d{4}", sy):
            sy = f"{sy[:4]}-{sy[-2:]}"
        cal = {**cal, "school_year": sy, "periods": list(cal.get("periods") or [])}
        if (cal.get("scope") or "").upper() == "ALL":
            alls[sy] = cal
        elif cal.get("scope") in codes:
            own[sy][cal["scope"]] = cal
    out = []
    for sy in set(alls) | set(own):
        base = alls.get(sy)
        for code in sorted(codes):
            c = own[sy].get(code)
            if c is None:
                if base is None or own[sy]:
                    continue
                c = {**base, "scope": code}
            elif base:
                c = {**c, "periods": base["periods"] + c["periods"],
                     "first_day": c.get("first_day") or base.get("first_day"),
                     "last_day": c.get("last_day") or base.get("last_day"),
                     "source_url": c.get("source_url") or base.get("source_url"),
                     "language": c.get("language") or base.get("language")}
            out.append(c)
    return out


# ---------------------------------------------------------------- school years and checks

def school_years(today: dt.date, calendar_year: bool, n: int = 4) -> list[str]:
    if calendar_year:
        return [str(today.year + i) for i in range(n)]
    y = today.year if today.month >= 8 else today.year - 1
    return [f"{y + i}-{(y + i + 1) % 100:02d}" for i in range(n)]


def year_window(sy: str) -> tuple[dt.date, dt.date]:
    if len(sy) == 4:
        y = int(sy)
        return dt.date(y - 1, 12, 1), dt.date(y + 1, 2, 28)
    y = int(sy[:4])
    return dt.date(y, 7, 1), dt.date(y + 1, 9, 30)


def d(s) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(s).strip()[:10])
    except (TypeError, ValueError):
        return None


def check(cal: dict, cc: str) -> tuple[list[dict], list[str]]:
    """Normalised periods and the reasons the calendar is implausible (empty when it is fine)."""
    errors, periods = [], []
    sy = cal["school_year"]
    lo, hi = year_window(sy)
    for p in cal.get("periods") or []:
        s, e = d(p.get("start_date")), d(p.get("end_date"))
        if not s or not e or e < s:
            errors.append(f"bad dates {p.get('start_date')}..{p.get('end_date')}")
            continue
        if s < lo or e > hi:
            errors.append(f"{p.get('name_en') or p.get('name_local')} {s}..{e} lies outside school year {sy}")
            continue
        kind = p.get("kind") if p.get("kind") in KINDS else "other"
        if kind == "break" and (e - s).days > 110:
            errors.append(f"{p.get('name_en')} lasts {(e - s).days} days")
            continue
        periods.append({**p, "kind": kind, "start": s, "end": e})
    uniq = {(p["start"], p["end"], p["kind"]): p for p in periods}
    periods = sorted(uniq.values(), key=lambda p: (p["start"], p["end"]))
    breaks = [p for p in periods if p["kind"] == "break"]
    for a, b in zip(breaks, breaks[1:]):
        if b["start"] <= a["end"]:
            errors.append(f"breaks overlap: {a['name_en']} and {b['name_en']}")
    if len(breaks) < 2:
        errors.append(f"only {len(breaks)} break(s)")
    if len(sy) == 7 and cc in EUROPE:
        y = int(sy[:4])
        if not any(p["start"] <= dt.date(y + 1, 1, 1) and p["end"] >= dt.date(y, 12, 24) for p in periods):
            errors.append("no break around Christmas")
        summer = any(p["kind"] == "break" and (p["end"] - p["start"]).days >= 25 and p["start"].month in (6, 7, 8)
                     for p in breaks)
        if not summer and not (d(cal.get("first_day")) and d(cal.get("last_day"))):
            errors.append("neither a summer break nor the first and last day of school")
    for k in ("first_day", "last_day"):
        if cal.get(k) and not (d(cal[k]) and lo <= d(cal[k]) <= hi):
            errors.append(f"{k} {cal[k]} outside school year {sy}")
    return periods, errors


def verified(cal: dict, periods: list[dict], mentions: set) -> tuple[int, int]:
    dates = [x for p in periods for x in ((p["start"], p["end"]) if p["start"] != p["end"] else (p["start"],))]
    dates += [d(cal[k]) for k in ("first_day", "last_day") if d(cal.get(k))]
    return sum((x.day, x.month) in mentions for x in dates), len(dates)


def compare(ours: list[tuple[dt.date, dt.date]], other: list[tuple[dt.date, dt.date]]) -> str:
    """agree | disagree | unrelated, for two lists of breaks; weekend shifts of two days are ignored."""
    matched, clash = 0, []
    for s, e in other:
        if any(abs((s - s2).days) <= 2 and abs((e - e2).days) <= 2 for s2, e2 in ours):
            matched += 1
        elif any(s2 <= e and e2 >= s for s2, e2 in ours):
            clash.append((s, e))
    if clash:
        return "disagree"
    return "agree" if matched >= 2 else "unrelated"


# ---------------------------------------------------------------- database

def load_scopes(cur, countries: set[str] | None, skip: set[str]):
    cur.execute("""
        select c.country_code::text, c.subdivision_code, c.authority_id::text, a.name, a.kind,
               coalesce(sd.name, c.subdivision_code), c.school_year, c.status, public.calendar_visible(c.id), c.id::text
          from public.school_calendars c
          left join public.education_authorities a on a.id = c.authority_id
          left join public.subdivisions sd on sd.code = c.subdivision_code
         where c.country_code <> 'US'""")
    scopes: dict[tuple, dict] = {}
    covered_sub: set[tuple] = set()
    for cc, sub, auth, aname, akind, sname, sy, status, visible, cid in cur.fetchall():
        if cc in skip or (countries and cc not in countries):
            continue
        key = (cc, sub, auth)
        s = scopes.setdefault(key, dict(cc=cc, sub=sub, auth=auth, auth_name=aname, auth_kind=akind,
                                        name=aname or (sname if sub else "nationwide"), years=set(), others=defaultdict(list)))
        if status in ("confirmed", "pending"):
            s["others"][sy].append(cid)
        if status == "confirmed" and visible:
            s["years"].add(sy)
            covered_sub.add((cc, sub, sy))
    return scopes, covered_sub


def other_breaks(cur, ids: list[str]) -> dict[str, list[tuple[dt.date, dt.date]]]:
    if not ids:
        return {}
    cur.execute("""select p.calendar_id::text, p.start_date, p.end_date, c.source_id
                     from public.school_calendar_periods p join public.school_calendars c on c.id = p.calendar_id
                    where p.calendar_id = any(%s::uuid[]) and p.kind = 'break'""", (ids,))
    out = defaultdict(list)
    for cid, s, e, src in cur.fetchall():
        out[(cid, src)].append((s, e))
    return out


# ---------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--countries", help="comma-separated, default: all with gaps")
    ap.add_argument("--max-calls", type=int, default=30, help="documents read by the model per run")
    ap.add_argument("--max-searches", type=int, default=10, help="web searches for new sources per run")
    ap.add_argument("--no-discover", action="store_true")
    ap.add_argument("--out")
    ap.add_argument("--report")
    ap.add_argument("--today")
    args = ap.parse_args()
    dsn = os.environ.get("DATABASE_URL")
    model = make_model()
    if not dsn or not model:
        print("DATABASE_URL and OPENAI_API_KEY (or ANTHROPIC_API_KEY) are required")
        return 2
    import psycopg

    today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()
    reg = json.load(open(SOURCES, encoding="utf-8"))
    conf = reg["countries"]
    skip = {cc for cc, c in conf.items() if c.get("skip")}
    only = {c.strip().upper() for c in args.countries.split(",")} if args.countries else None
    out_path = args.out or os.path.join(ROOT, "data", "editorial", f"auto-{today:%Y-%m-%d}.json")
    log: list[str] = []
    stats = Counter()
    results: dict[str, dict] = {}  # calendar id -> calendar
    rejected: list[str] = []
    candidates: list[str] = []
    learned: list[dict] = []
    unresolved: dict[str, list[str]] = defaultdict(list)
    errors_model: list[str] = []  # the model could not be used: shown on top, and the run fails

    with psycopg.connect(dsn) as conn:
        conn.read_only = True
        cur = conn.cursor()
        scopes, covered_sub = load_scopes(cur, only, skip)

        # what to research: scopes whose current or next school year is missing
        targets: dict[str, list[dict]] = defaultdict(list)
        cy_country = {cc for (cc, _, _), s in scopes.items() for y in s["others"] if len(y) == 4} | CALENDAR_YEAR
        for key, s in scopes.items():
            cc = s["cc"]
            years = school_years(today, cc in cy_country)
            missing = [y for y in years if y not in s["years"]
                       and not (s["auth"] is None and (cc, s["sub"], y) in covered_sub)]
            if years[0] in missing or years[1] in missing:
                s["want"] = missing
                s["code"] = (s["sub"] or cc) if s["auth"] is None else None
                targets[cc].append(s)
        order = sorted(targets, key=lambda c: (c not in PRIORITY, PRIORITY.index(c) if c in PRIORITY else 0,
                                               -len(targets[c])))
        stats["regions_missing"] = sum(len(v) for v in targets.values())

        calls = searches = 0
        for cc in order:
            items = targets[cc]
            cfg = conf.get(cc, {})
            patterns = cfg.get("official", [])
            for i, s in enumerate(x for x in items if x["code"] is None):
                s["code"] = f"A{i + 1}"
            by_code = {s["code"]: s for s in items}
            years = sorted({y for s in items for y in s["want"]})

            got: dict[tuple, list[dict]] = defaultdict(list)  # (code, year) -> calendars from different URLs
            discovered: set[str] = set()
            searched: set[str] = set()
            delivered: set[str] = set()  # scope codes with at least one readable document

            def discover(todo: list[dict]) -> dict[str, set[str]]:
                nonlocal searches
                plan: dict[str, set[str]] = defaultdict(set)
                todo = [s for s in todo if s["code"] not in searched]
                for chunk in [todo[i:i + 8] for i in range(0, len(todo), 8)]:
                    if args.no_discover or searches >= args.max_searches:
                        break
                    searches += 1
                    searched.update(s["code"] for s in chunk)
                    regions = "\n".join(f"- {s['code']}: {s['name']}" for s in chunk)
                    prompt = (f"Country: {cc} ({cfg.get('name', cc)})\nSchool years: {', '.join(years)}\n"
                              f"{cfg.get('hint', '')}\nScopes:\n{regions}")
                    try:
                        found, cited = model.search(DISCOVER_SYSTEM, prompt)
                    except ModelError as e:
                        errors_model.append(f"{cc}: web search failed: {e}")
                        continue
                    listed = found.get("sources", []) if isinstance(found, dict) else []
                    for f in listed:
                        url = (f.get("url") or "").strip()
                        codes = [c for c in f.get("scopes", []) if c in by_code] or [s["code"] for s in chunk]
                        if not url.startswith("http"):
                            continue
                        if is_official(url, patterns):
                            plan[url].update(codes)
                            discovered.add(url)
                        else:
                            candidates.append(f"{cc} {', '.join(codes)}: {url}")
                    for url in cited:  # pages the search cited; official ones are read if the answer listed none
                        if is_official(url, patterns):
                            if not listed:
                                plan[url].update(s["code"] for s in chunk)
                                discovered.add(url)
                        elif not AGGREGATORS.search(url):
                            candidates.append(f"{cc} (cited): {url}")
                return plan

            def read(plan: dict[str, set[str]]) -> None:
                nonlocal calls
                for url, codes in plan.items():
                    if calls >= args.max_calls:
                        log.append(f"{cc}: stopped at the limit of {args.max_calls} documents for this run")
                        return
                    time.sleep(1)
                    parts = fetch_document(url, years, log)
                    text = "\n\n".join(f"=== Document part: {u} ===\n{t}" for u, t in parts if t.strip())
                    if not text or not date_mentions(text):
                        if parts:
                            log.append(f"{cc}: no dates in {url}")
                        stats["documents_unreadable"] += 1
                        continue
                    mentions = date_mentions(text)
                    regions = "\n".join(f"- {c}: {by_code[c]['name']}" for c in sorted(codes))
                    user = (f"Country: {cc}\nSchool years wanted: {', '.join(years)} "
                            f"({'calendar years' if cc in cy_country else 'from summer to summer, e.g. 2026-27'})\n"
                            f"Scopes:\n{regions}\n\nDocument:\n{shorten(text)}")
                    calls += 1
                    try:
                        data = model.extract(EXTRACT_SYSTEM, user)
                    except (ModelError, json.JSONDecodeError, KeyError) as e:
                        errors_model.append(f"{cc}: reading {url} failed: {e}")
                        continue
                    stats["documents_read"] += 1
                    delivered.update(codes)
                    urls = {u for u, _ in parts}
                    found_here = 0
                    for cal in merge_all(data.get("calendars", []), codes):
                        code, sy = cal["scope"], cal["school_year"]
                        if sy not in by_code[code]["want"]:
                            continue
                        periods, errors = check(cal, cc)
                        if errors:
                            rejected.append(f"{cc} {by_code[code]['name']} {sy} ({host(url)}): {'; '.join(errors[:3])}")
                            stats["rejected"] += 1
                            continue
                        ok, total = verified(cal, periods, mentions)
                        src = cal.get("source_url") if cal.get("source_url") in urls else url
                        found_here += 1
                        got[(code, sy)].append(dict(cal=cal, periods=periods, ok=ok, total=total, url=src, page=url,
                                                    official=is_official(src, patterns) or url not in discovered,
                                                    language=(cal.get("language") or cfg.get("lang") or "en")[:2].lower()))
                    if url in discovered and found_here:
                        learned.append({"country": cc, "url": url,
                                        "scopes": sorted(by_code[c]["name"] if by_code[c]["auth"] else c for c in codes)})

            # 1. listed sources; scopes without one are searched for on the web
            plan: dict[str, set[str]] = defaultdict(set)
            for src in cfg.get("sources", []):
                for s in items:
                    if src.get("scopes", "*") == "*" or s["code"] in src["scopes"] or s["name"] in src["scopes"]:
                        plan[src["url"]].add(s["code"])
            for url, codes in discover([s for s in items if not any(s["code"] in v for v in plan.values())]).items():
                plan[url].update(codes)
            # 2. read every document once, for all scopes it should cover
            read(plan)
            # 2b. scopes whose documents could not be read (blocked, moved, no dates): search for another source
            retry = discover([s for s in items if s["code"] not in delivered])
            read({u: c for u, c in retry.items() if u not in plan})

            # 3. decide, compare with what the database already has
            others = other_breaks(cur, [cid for s in items for y in s["want"] for cid in s["others"].get(y, [])])
            for s in items:
                for sy in s["want"]:
                    cands = got.get((s["code"], sy))
                    if not cands:
                        if sy in school_years(today, cc in cy_country)[:2]:
                            unresolved[cc].append(f"{s['name']} {sy}")
                        continue
                    cands.sort(key=lambda c: (c["ok"] == c["total"], c["official"], c["ok"]), reverse=True)
                    best = cands[0]
                    cid = str(uuid.uuid5(NS, f"auto|{cc}|{s['sub'] or ''}|{s['auth'] or ''}|{sy}"))
                    ours = [(p["start"], p["end"]) for p in best["periods"] if p["kind"] == "break"]
                    verdicts = [(f"a second page ({host(c['url'])})",
                                 compare(ours, [(p["start"], p["end"]) for p in c["periods"] if p["kind"] == "break"]))
                                for c in cands[1:]]
                    verdicts += [(src, compare(ours, b)) for (oid, src), b in others.items()
                                 if oid in s["others"].get(sy, []) and oid != cid]
                    agree = [who for who, v in verdicts if v == "agree"]
                    clash = [who for who, v in verdicts if v == "disagree"]
                    full = best["ok"] == best["total"]
                    if clash:
                        status, why = "pending", "differs from " + ", ".join(clash)
                    elif (best["official"] and full) or agree:
                        status = "confirmed"
                        why = "; ".join(x for x in ("all dates found in the official document"
                                                    if best["official"] and full else "",
                                                    "agrees with " + ", ".join(agree) if agree else "") if x)
                    else:
                        status = "pending"
                        why = (f"{best['total'] - best['ok']} of {best['total']} dates not found in the document"
                               if not full else "not on an official domain")
                    stats[f"calendars_{status}"] += 1
                    lang = best["language"]
                    results[cid] = {
                        "id": cid, "country_code": cc, "subdivision_code": s["sub"], "authority": s["auth_name"],
                        "authority_id": s["auth"], "authority_kind": s["auth_kind"] or "other", "authority_ext": {},
                        "school_year": sy, "status": status, "source_url": best["url"],
                        "first_day": str(d(best["cal"].get("first_day")) or "") or None,
                        "last_day": str(d(best["cal"].get("last_day")) or "") or None,
                        "notes": (f"Automatically extracted from {host(best['url'])} ({model.provider} {model.model}); "
                                  f"{best['ok']} of {best['total']} dates found in the document; {why}."),
                        "periods": [{"start_date": str(p["start"]), "end_date": str(p["end"]), "kind": p["kind"],
                                     "label": (p.get("name_local") or p.get("name_en") or "").strip()[:200],
                                     "names": {k: v.strip() for k, v in
                                               {"en": p.get("name_en") or "", lang: p.get("name_local") or ""}.items()
                                               if v and v.strip()}}
                                    for p in best["periods"]],
                        "_label": f"{s['name']} {sy}", "_why": why,
                    }

    # ---- write the editorial file, the learned sources and the report
    if results:
        payload = {"dataset": f"auto-research-{today:%Y-%m-%d}", "retrieved": str(today),
                   "method": (f"Automatic research: official documents read by {model.provider} {model.model}, "
                              "dates checked against the document text and other sources (scripts/auto_research.py)."),
                   "calendars": [{k: v for k, v in c.items() if not k.startswith("_")} for c in results.values()]}
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=1)
            f.write("\n")
    if learned:
        for item in learned:
            c = conf.setdefault(item["country"], {})
            srcs = c.setdefault("sources", [])
            if not any(x["url"] == item["url"] for x in srcs):
                srcs.append({"url": item["url"], "scopes": item["scopes"], "learned": str(today)})
        with open(SOURCES, "w", encoding="utf-8") as f:
            json.dump(reg, f, ensure_ascii=False, indent=2)
            f.write("\n")

    u = model.usage
    lines = [f"## Automatic research, {today:%d %b %Y}", "",
             f"{stats['regions_missing']} regions without the current or next school year. "
             f"Read {stats['documents_read']} documents, {u['searches']} web searches "
             f"({model.provider} {model.model}, {u['input']:,} input and {u['output']:,} output tokens).", "",
             f"- ✅ confirmed: {stats['calendars_confirmed']}",
             f"- 🟡 pending (served only with include=pending): {stats['calendars_pending']}",
             f"- ❌ rejected as implausible: {stats['rejected']}", ""]
    if errors_model:
        lines[2:2] = [f"> [!CAUTION]\n> The language model could not be used ({len(errors_model)} failed requests). "
                      f"First error: {errors_model[0]}", ""]
    if results:
        lines += ["| Region | Status | Source | Why |", "|---|---|---|---|"]
        for c in sorted(results.values(), key=lambda c: (c["country_code"], c["_label"])):
            lines.append(f"| {c['country_code']} {c['_label']} | {'✅' if c['status'] == 'confirmed' else '🟡'} "
                         f"| [{host(c['source_url'])}]({c['source_url']}) | {c['_why']} |")
        lines.append("")
    if rejected:
        lines += ["### Rejected", ""] + [f"- {r}" for r in rejected[:40]] + [""]
    if unresolved:
        lines += ["### Still missing (no official document with these dates found)", ""]
        lines += [f"- **{cc}**: {', '.join(v[:20])}{f' and {len(v) - 20} more' if len(v) > 20 else ''}"
                  for cc, v in unresolved.items()] + [""]
    if learned:
        lines += ["### New sources saved", ""] + [f"- {x['country']}: {x['url']}" for x in learned] + [""]
    if candidates:
        lines += ["### Candidates not used (not on an official domain)",
                  "Add the domain to `official` in data/research/sources.json if it is the authority's own site.", ""]
        lines += [f"- {c}" for c in list(dict.fromkeys(candidates))[:30]] + [""]
    if log:
        lines += ["<details><summary>Log</summary>", ""] + [f"- {x}" for x in log[:80]] + ["", "</details>", ""]
    report = "\n".join(lines) + "\n"
    print(report)
    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            f.write(report)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(report)
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"file={os.path.relpath(out_path, ROOT) if results else ''}\n")
    if errors_model and not stats["documents_read"]:
        print("::error::The language model could not be used: " + errors_model[0].replace("\n", " "))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
