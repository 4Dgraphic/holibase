"""
Build Holibase library data from python-holidays.

Produces normalised rows for
  - public_holidays        (every category except "school")
  - school_calendars + school_calendar_periods (category "school", grouped into periods)
  - subdivisions / countries metadata needed by the rows above

Rules (see README "Data model in five rules"):
  * subdivision_code NULL holds the national set; each subdivision holds its COMPLETE set,
    nationwide days included with scope = 'national'.
  * Observed / estimated suffixes are stripped from names and stored as flags.
  * Several holidays on one date ("A; B") become separate rows.
  * names = {language tag: name} for every language python-holidays offers ("en_US" -> "en-US").

Used by scripts/sync.py (database sync) and scripts/export.py (CSV / static JSON).
"""
from __future__ import annotations

import datetime as dt
import re
import unicodedata
import uuid
from dataclasses import dataclass, field
from typing import Iterable, Iterator

import holidays
from holidays import country_holidays

SOURCE_ID = "python-holidays"
SOURCE_VERSION = holidays.__version__
SCHOOL_CATEGORY = "school"
# Countries whose school year is the calendar year (southern hemisphere)
CALENDAR_YEAR_SCHOOL = {"AU", "NZ", "ZA", "BR", "AR", "CL", "UY", "PY"}
CAL_NAMESPACE = uuid.UUID("6f1d3c52-7f0e-4b8e-9d0a-3b8c2a4e6d11")  # Holibase library calendars


def lang_tag(lang: str) -> str:
    return lang.replace("_", "-")


# ------------------------------------------------------------------ name parsing

def _label_patterns(h) -> list[tuple[re.Pattern, bool, bool]]:
    """Regexes for '%s (observed)' etc. in the instance's language -> (pattern, observed, estimated)."""
    out = []
    for attr, obs, est in (
        ("observed_estimated_label", True, True),
        ("observed_label", True, False),
        ("estimated_label", False, True),
    ):
        tpl = getattr(h, attr, None)
        if not tpl:
            continue
        try:
            tpl = h.tr(tpl)
        except Exception:
            pass
        if "%s" not in tpl:
            continue
        pre, post = tpl.split("%s", 1)
        if not pre.strip() and not post.strip():
            continue  # label without suffix ("%s"): nothing to strip
        out.append((re.compile("^" + re.escape(pre) + "(.+?)" + re.escape(post) + "$"), obs, est))
    return out


def _split(raw: str) -> list[str]:
    return [p.strip() for p in raw.split(";") if p.strip()]


def _strip(name: str, patterns) -> tuple[str, bool, bool]:
    for pat, obs, est in patterns:
        m = pat.match(name)
        if m:
            return m.group(1).strip(), obs, est
    return name, False, False


@dataclass
class Entry:
    date: dt.date
    category: str
    local_name: str
    is_observed: bool
    is_estimated: bool
    names: dict[str, str] = field(default_factory=dict)


def _entries(cc: str, subdiv: str | None, years: list[int], category: str, info) -> list[Entry]:
    """All holidays of one scope and one category, with names in every supported language.
    Countries without translations get {"en": local_name}."""
    base = country_holidays(cc, subdiv=subdiv, years=years, categories=(category,))
    if not base:
        return []
    base_pat = _label_patterns(base)
    # Days that exist only because of an observance rule (substitute / moved holidays)
    try:
        plain = country_holidays(cc, subdiv=subdiv, years=years, categories=(category,), observed=False)
        plain_keys = {(d, _strip(p, base_pat)[0]) for d, raw in plain.items() for p in _split(raw)}
    except TypeError:
        plain_keys = None
    entries: list[Entry] = []
    index: dict[tuple[dt.date, int], Entry] = {}
    for d, raw in sorted(base.items()):
        for i, part in enumerate(_split(raw)):
            name, obs, est = _strip(part, base_pat)
            if plain_keys is not None and (d, name) not in plain_keys:
                obs = True
            e = Entry(d, category, name, obs, est)
            entries.append(e)
            index[(d, i)] = e

    if not info["languages"]:
        for e in entries:
            e.names = {"en": e.local_name}
        return entries

    default = info["default_language"]
    for lang in info["languages"]:
        h = country_holidays(cc, subdiv=subdiv, years=years, categories=(category,), language=lang)
        pat = _label_patterns(h)
        tag = lang_tag(lang)
        # Positional fallback, only for dates with exactly one holiday in both languages
        parts = {d: [_strip(p, pat)[0] for p in _split(raw)] for d, raw in h.items()}
        for (d, i), e in index.items():
            if lang == default:
                e.names[tag] = e.local_name
                continue
            # Translate by message id: python-holidays uses the default-language name as msgid.
            # This keeps translations attached to the right holiday when several share a date.
            t = h.tr(e.local_name)
            day = parts.get(d, [])
            if t != e.local_name or t in day:
                e.names[tag] = t  # translated, or the name is identical in this language
            elif len(day) == 1 and len(_split(base[d])) == 1:
                e.names[tag] = day[0]  # formatted names (e.g. "Day off (substituted from ...)")
    return entries


# ------------------------------------------------------------------ countries

def country_info(cc: str) -> dict:
    h = country_holidays(cc)
    return {
        "code": cc,
        "default_language": h.default_language,
        "languages": list(h.supported_languages or ()),
        "categories": sorted(h.supported_categories or ("public",)),
        "subdivisions": list(h.subdivisions or ()),
    }


def supported_countries() -> list[str]:
    return sorted(holidays.list_supported_countries(include_aliases=False))


def subdivision_code(cc: str, sd: str) -> str:
    """ISO-style code; python-holidays' named areas become slugs ("São Paulo Capital" -> BR-SAO-PAULO-CAPITAL)."""
    ascii_sd = unicodedata.normalize("NFKD", sd).encode("ascii", "ignore").decode()
    return cc + "-" + re.sub(r"\s+", "-", ascii_sd.strip()).upper()


# ------------------------------------------------------------------ public holidays

def public_holiday_rows(cc: str, years: list[int], info: dict | None = None) -> Iterator[dict]:
    info = info or country_info(cc)
    default_lang = lang_tag(info["default_language"]) if info["default_language"] else "en"
    cats = [c for c in info["categories"] if c != SCHOOL_CATEGORY]

    national: dict[str, list[Entry]] = {c: _entries(cc, None, years, c, info) for c in cats}
    national_keys = {(e.date, e.category, e.local_name) for c in cats for e in national[c]}

    def row(e: Entry, sub: str | None, scope: str) -> dict:
        return {
            "country_code": cc,
            "subdivision_code": sub,
            "date": e.date.isoformat(),
            "category": e.category,
            "scope": scope,
            "local_name": e.local_name,
            "default_language": default_lang,
            "names": e.names,
            "is_observed": e.is_observed,
            "is_estimated": e.is_estimated,
        }

    for c in cats:
        for e in national[c]:
            yield row(e, None, "national")

    for sd in info["subdivisions"]:
        code = subdivision_code(cc, sd)
        for c in cats:
            for e in _entries(cc, sd, years, c, info):
                scope = "national" if (e.date, e.category, e.local_name) in national_keys else "regional"
                yield row(e, code, scope)


# ------------------------------------------------------------------ school holidays

def school_year(cc: str, d: dt.date, is_summer: bool = False) -> str:
    """School year a period belongs to. Northern hemisphere: August starts a new year, except the
    summer break, which always closes the year that ends (Bavaria's Sommerferien start in August)."""
    if cc in CALENDAR_YEAR_SCHOOL:
        return str(d.year)
    y = d.year if d.month >= 8 and not is_summer else d.year - 1
    return f"{y}-{(y + 1) % 100:02d}"


def _is_summer(period: dict) -> bool:
    en = next((v for k, v in period["names"].items() if k.split("-")[0] == "en"), "")
    return "summer" in en.lower() or "sommer" in period["label"].lower()


def _periods(entries: list[Entry]) -> list[dict]:
    """Group consecutive days with the same label into periods."""
    out: list[dict] = []
    for e in sorted(entries, key=lambda x: (x.date, x.local_name)):
        last = out[-1] if out else None
        if last and last["label"] == e.local_name and e.date == last["_end"] + dt.timedelta(days=1):
            last["_end"] = e.date
            continue
        out.append({"_start": e.date, "_end": e.date, "label": e.local_name, "names": dict(e.names)})
    for p in out:
        p["start_date"] = p.pop("_start").isoformat()
        end = p.pop("_end")
        p["end_date"] = end.isoformat()
        p["kind"] = "break" if p["start_date"] != p["end_date"] else "holiday"
    return out


# ------------------------------------------------------------------ Germany: official names and extra days
# python-holidays takes the German dates from the KMK table (checked against it for 2026/27) but files every
# period under six generic names ("Oster-/Frühjahrsferien", "Himmelfahrts-/Pfingstferien"), single school-free
# days included. The states' own names are restored here, and the school-free days that the KMK table leaves
# out are added: Buß- und Bettag in Bavaria (BayFTG Art. 4: no lessons at any school) and Brandenburg's
# variable holidays (they apply unless the school conference decides otherwise).

def _easter(year: int) -> dt.date:
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    g = (8 * b + 13) // 25
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    return dt.date(year, month, (h + l - 7 * m + 114) % 31 + 1)


_DE_NAMES = {  # German name -> English name
    "Herbstferien": "Autumn Break", "Weihnachtsferien": "Christmas Break", "Winterferien": "Winter Break",
    "Frühjahrsferien": "Spring Break", "Osterferien": "Easter Break", "Pfingstferien": "Whitsun Break",
"Sommerferien": "Summer Break",
    "Brückentag nach Christi Himmelfahrt": "Bridge Day after Ascension", "Halbjahrespause": "Half-Year Break",
    "Unterrichtsfreier Tag": "School-free Day", "Buß- und Bettag": "Day of Repentance and Prayer",
    "Variabler Ferientag": "Variable School Holiday",
}
DE_BB_VARIABLE_DAYS = [  # VV Schulbetrieb, Anlage 1 (bravors.brandenburg.de), school years 2025/26 to 2029/30
    "2026-05-15", "2027-05-07", "2028-05-26", "2028-10-30", "2029-04-30", "2029-05-11", "2030-05-31"]


def _de_name(sub: str | None, label: str, start: dt.date, end: dt.date) -> str:
    single = start == end
    if label == "Sommerferien" or label == "Weihnachtsferien":
        return label
    easter = _easter(start.year)
    ascension, pentecost = easter + dt.timedelta(days=39), easter + dt.timedelta(days=49)
    if single and start == ascension + dt.timedelta(days=1):
        return "Brückentag nach Christi Himmelfahrt"
    if label == "Himmelfahrts-/Pfingstferien":  # the states call a break in May or June "Pfingstferien"
        if not single or pentecost - dt.timedelta(days=3) <= start <= pentecost + dt.timedelta(days=3):
            return "Pfingstferien"
        return "Unterrichtsfreier Tag"
    if label == "Oster-/Frühjahrsferien":
        if start <= easter + dt.timedelta(days=14) and end >= easter - dt.timedelta(days=14):
            return "Osterferien"
        return "Unterrichtsfreier Tag" if single else "Frühjahrsferien"
    if label == "Winterferien" and single:
        return "Halbjahrespause" if sub == "DE-HH" else "Unterrichtsfreier Tag"
    if label == "Herbstferien" and single:
        return "Unterrichtsfreier Tag"
    return label


def _de_period(start: dt.date, name: str) -> dict:
    return {"start_date": start.isoformat(), "end_date": start.isoformat(), "kind": "holiday", "label": name,
            "names": {"de": name, "en": _DE_NAMES[name], "en-US": _DE_NAMES[name]}}


def _refine_de(sub: str | None, periods: list[dict], years: list[int]) -> list[dict]:
    for p in periods:
        name = _de_name(sub, p["label"], dt.date.fromisoformat(p["start_date"]), dt.date.fromisoformat(p["end_date"]))
        if name != p["label"]:
            p["label"] = name
            p["names"] = {**p["names"], "de": name, "en": _DE_NAMES[name], "en-US": _DE_NAMES[name]}
            p["names"] = {k: v for k, v in p["names"].items() if k in ("de", "en", "en-US")}  # other languages kept the generic name
    extra = []
    if sub in ("DE-BY", "DE-AUGSBURG"):  # the Wednesday before 23 November
        for y in years:
            d = dt.date(y, 11, 22)
            extra.append(_de_period(d - dt.timedelta(days=(d.weekday() - 2) % 7), "Buß- und Bettag"))
    if sub == "DE-BB":
        extra += [_de_period(dt.date.fromisoformat(d), "Variabler Ferientag") for d in DE_BB_VARIABLE_DAYS
                  if dt.date.fromisoformat(d).year in years]
    for e in extra:
        if not any(p["start_date"] <= e["start_date"] <= p["end_date"] for p in periods):
            periods.append(e)
    return sorted(periods, key=lambda p: p["start_date"])


def calendar_id(cc: str, sub: str | None, year: str) -> str:
    return str(uuid.uuid5(CAL_NAMESPACE, f"{SOURCE_ID}|{cc}|{sub or ''}|{year}"))


def school_calendar_rows(cc: str, years: list[int], info: dict | None = None) -> Iterator[dict]:
    """One dict per calendar: {country_code, subdivision_code, school_year, periods: [...]}"""
    info = info or country_info(cc)
    if SCHOOL_CATEGORY not in info["categories"]:
        return
    scopes: list[tuple[str | None, list[Entry]]] = []
    national = _entries(cc, None, years, SCHOOL_CATEGORY, info)
    nat_set = {(e.date, e.local_name) for e in national}
    if national:
        scopes.append((None, national))
    for sd in info["subdivisions"]:
        ents = _entries(cc, sd, years, SCHOOL_CATEGORY, info)
        if ents and {(e.date, e.local_name) for e in ents} != nat_set:
            scopes.append((subdivision_code(cc, sd), ents))

    for sub, ents in scopes:
        by_year: dict[str, list[dict]] = {}
        periods = _periods(ents)
        if cc == "DE":
            periods = _refine_de(sub, periods, years)
        for p in periods:
            start = dt.date.fromisoformat(p["start_date"])
            summer = start.month in (8, 9) and _is_summer(p)
            by_year.setdefault(school_year(cc, start, summer), []).append(p)
        for year, periods in sorted(by_year.items()):
            yield {
                "id": calendar_id(cc, sub, year),
                "country_code": cc,
                "subdivision_code": sub,
                "school_year": year,
                "periods": periods,
            }


# ------------------------------------------------------------------ convenience

def build(countries: Iterable[str], years: list[int]):
    """Yield (info, public_rows, school_calendars) per country."""
    for cc in countries:
        info = country_info(cc)
        yield info, list(public_holiday_rows(cc, years, info)), list(school_calendar_rows(cc, years, info))
