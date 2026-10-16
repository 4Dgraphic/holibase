"""
Static pages generated from web/.cache/snapshot.json (see snapshot.py):

    /school-holidays/                     all countries with school holidays
    /school-holidays/{cc}/                one country: its regions, zones or districts (or its calendar)
    /school-holidays/{cc}/{slug}/         one region, zone or school district
    /public-holidays/                     all countries
    /public-holidays/{cc}/                one country, this year and next

Every page carries its dates in the HTML, so search engines and AI crawlers can read them without
running JavaScript. Used by build.py; nothing here talks to the network.
"""
from __future__ import annotations

import datetime as dt
import html
import json
import re
import unicodedata
import urllib.parse
from collections import defaultdict

from babel import Locale

API = "https://api.holibase.org"
SITE = "https://holibase.org"
TERRITORIES = Locale("en").territories

# English names for regions stored under their local name or an ISO code.
REGION_EN = {
    "DE-BW": "Baden-Württemberg", "DE-BY": "Bavaria", "DE-BE": "Berlin", "DE-BB": "Brandenburg", "DE-HB": "Bremen",
    "DE-HH": "Hamburg", "DE-HE": "Hesse", "DE-MV": "Mecklenburg-Western Pomerania", "DE-NI": "Lower Saxony",
    "DE-NW": "North Rhine-Westphalia", "DE-RP": "Rhineland-Palatinate", "DE-SL": "Saarland", "DE-SN": "Saxony",
    "DE-ST": "Saxony-Anhalt", "DE-SH": "Schleswig-Holstein", "DE-TH": "Thuringia",
    "AT-1": "Burgenland", "AT-2": "Carinthia", "AT-3": "Lower Austria", "AT-4": "Upper Austria", "AT-5": "Salzburg",
    "AT-6": "Styria", "AT-7": "Tyrol", "AT-8": "Vorarlberg", "AT-9": "Vienna",
    "CH-ZH": "Zurich", "CH-GE": "Geneva", "CH-LU": "Lucerne", "CH-SG": "St. Gallen", "CH-FR": "Fribourg",
    "CH-GR": "Graubünden", "CH-TI": "Ticino", "CH-VD": "Vaud", "CH-VS": "Valais", "CH-NE": "Neuchâtel",
    "CH-BS": "Basel-Stadt", "CH-BL": "Basel-Landschaft", "CH-STADT-ZURICH": "City of Zurich",
    "FR-971": "Guadeloupe", "FR-972": "Martinique", "FR-973": "French Guiana", "FR-974": "Réunion", "FR-976": "Mayotte",
    "FR-NC": "New Caledonia", "FR-PF": "French Polynesia", "FR-PM": "Saint Pierre and Miquelon",
    "FR-WF": "Wallis and Futuna", "FR-BL": "Saint Barthélemy", "FR-MF": "Saint Martin", "FR-6AE": "Alsace",
}
ORIGIN = {
    "official": "Official open data",
    "library": "python-holidays",
    "editorial": "Researched by Holibase",
    "community": "Community submission",
}
KIND = {"break": "School holiday", "holiday": "Day off", "teacher_day": "No school for students",
        "early_release": "Early release", "other": "No school"}


# ---------------------------------------------------------------- helpers

esc = lambda s: html.escape(str(s if s is not None else ""), quote=True)  # noqa: E731


def d(s: str) -> dt.date:
    return dt.date.fromisoformat(s[:10])


def day(x: dt.date) -> str:
    return f"{x:%a} {x.day} {x:%b %Y}"


def cell(x: dt.date) -> str:
    """Table date; the weekday is hidden on narrow screens."""
    return f'<span class="wd">{x:%a} </span>{x.day} {x:%b %Y}'


def day_long(x: dt.date) -> str:
    return f"{x:%A} {x.day} {x:%B %Y}"


def day_short(x: dt.date) -> str:
    return f"{x.day} {x:%b}"


def span(a: dt.date, b: dt.date) -> str:
    if a == b:
        return day(a)
    if a.year == b.year:
        return f"{a:%a} {day_short(a)} – {day(b)}"
    return f"{day(a)} – {day(b)}"


def slugify(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "x"


def country_name(cc: str) -> str:
    return TERRITORIES.get(cc, cc)


def school_year_label(sy: str) -> str:
    return sy.replace("-", "/")


def host(url: str | None) -> str:
    return urllib.parse.urlparse(url).hostname or "" if url else ""


def feed_links(path: str, name: str) -> dict:
    https = API + path
    webcal = "webcal:" + https[len("https:"):]
    return {
        "https": https,
        "apple": webcal,
        "google": "https://calendar.google.com/calendar/render?cid=" + urllib.parse.quote(webcal, safe=""),
        "outlook": "https://outlook.live.com/calendar/0/addfromweb?url=" + urllib.parse.quote(https, safe="")
                   + "&name=" + urllib.parse.quote(name, safe=""),
    }


def subscribe_html(label: str, path: str, name: str) -> str:
    f = feed_links(path, name)
    return f"""<div><p class="body-s muted" style="margin: 0 0 8px">{esc(label)}</p>
<div class="row">
<a class="btn btn-primary btn-sm" href="{esc(f['apple'])}">Apple Calendar</a>
<a class="btn btn-secondary btn-sm" href="{esc(f['google'])}" rel="noopener" target="_blank">Google Calendar</a>
<a class="btn btn-secondary btn-sm" href="{esc(f['outlook'])}" rel="noopener" target="_blank">Outlook</a>
<a class="btn btn-secondary btn-sm" href="{esc(f['https'])}" download>Download .ics</a>
</div></div>"""


def breadcrumb(items: list[tuple[str, str]]) -> tuple[str, dict]:
    """items: (name, path). Returns the visible trail and its JSON-LD."""
    links = " <span aria-hidden=\"true\">/</span> ".join(
        f'<a href="{esc(p)}">{esc(n)}</a>' if i < len(items) - 1 else f'<span aria-current="page">{esc(n)}</span>'
        for i, (n, p) in enumerate(items))
    ld = {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": i + 1, "name": n, "item": SITE + p} for i, (n, p) in enumerate(items)]}
    return f'<nav class="crumbs" aria-label="Breadcrumb">{links}</nav>', ld


def faq_html(faq: list[tuple[str, str]]) -> tuple[str, dict | None]:
    if not faq:
        return "", None
    body = "".join(f"<h3>{esc(q)}</h3><p>{esc(a)}</p>" for q, a in faq)
    ld = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]}
    return f'<section class="gen-section"><h2>Frequently asked questions</h2>{body}</section>', ld


def page(path, title, description, body, nav="", ld=(), lastmod=None):
    return {"path": path, "title": title, "description": description, "body": body, "nav": nav,
            "ld": [x for x in ld if x], "theme": "dark", "lastmod": lastmod}


# ---------------------------------------------------------------- school holidays

class Scope:
    def __init__(self, raw: dict):
        self.raw = raw
        self.cc = raw["cc"]
        self.sub = raw.get("sub")
        self.auth = raw.get("auth")
        self.region = self.sub or raw.get("auth_sub")
        self.region_name = REGION_EN.get(self.region) or raw.get("sub_name") or ""
        if re.fullmatch(r"[A-Z]{2}", self.region_name or ""):
            self.region_name = country_name(self.region_name)
        self.country = country_name(self.cc)
        self.national = not self.sub and not self.auth
        self.name = raw.get("auth_name") or (self.region_name if self.sub else self.country)
        self.local_name = raw.get("sub_name") if self.sub and raw.get("sub_name") not in (None, self.name) and not re.fullmatch(r"[A-Z]{2}", raw.get("sub_name") or "") else None
        self.periods = [p for p in raw["periods"] if p["status"] == "confirmed"]
        self.calendars = [c for c in raw["calendars"] if c["status"] == "confirmed"]
        self.public = raw.get("public") or []
        self.slug = ""
        self.key = f"auth:{self.auth}" if self.auth else (self.sub or self.cc)

    @property
    def url(self):
        return f"/school-holidays/{self.cc.lower()}/" + (f"{self.slug}/" if self.slug else "")

    def kept(self, today: dt.date):
        """Periods of school years that are not over yet."""
        by_year = defaultdict(list)
        for p in self.periods:
            by_year[p["school_year"]].append(p)
        years = [y for y, ps in by_year.items() if max(d(p["end_date"]) for p in ps) >= today]
        return {y: sorted(by_year[y], key=lambda p: p["start_date"]) for y in sorted(years)}

    def next_break(self, today: dt.date):
        upcoming = [p for p in self.periods if d(p["end_date"]) >= today and p["kind"] != "early_release"]
        breaks = [p for p in upcoming if p["kind"] == "break"]
        return (breaks or upcoming or [None])[0]

    def feed_path(self):
        q = f"authority={self.auth}&" if self.auth else f"subdivision={self.sub}&" if self.sub else ""
        return f"/v1/school-holidays/{self.cc}.ics?{q}lang=en"

    def app_url(self):
        q = {"country": self.cc}
        if self.auth:
            q["authority"] = self.auth
        elif self.sub:
            q["subdivision"] = self.sub
        return "/calendar/?" + urllib.parse.urlencode(q)

    def where(self):
        parts = [self.raw.get("auth_city"), self.region_name if self.auth else None, self.country]
        return ", ".join(p for p in parts if p and p != self.name)


def assign_slugs(scopes: list[Scope]) -> None:
    by_cc = defaultdict(list)
    for s in scopes:
        by_cc[s.cc].append(s)
    for cc, group in by_cc.items():
        if len(group) == 1 and group[0].national:
            continue  # the country page is the calendar
        seen = {}
        for s in sorted(group, key=lambda s: (s.national, s.name)):
            base = "nationwide" if s.national else slugify(s.name)
            slug = base
            if slug in seen:
                slug = f"{base}-{slugify(s.raw.get('auth_city') or s.region_name or '')}".strip("-")
            if slug in seen:
                slug = f"{base}-{str(s.auth)[:6]}"
            seen[slug] = s
            s.slug = slug


def years_label(dates: list[dt.date]) -> str:
    ys = sorted({x.year for x in dates})[:2]
    return " and ".join(str(y) for y in ys)


def scope_page(s: Scope, siblings: list[Scope], today: dt.date) -> dict:
    kept = s.kept(today)
    all_kept = [p for ps in kept.values() for p in ps]
    years = years_label([d(p["start_date"]) for p in all_kept] or [today])
    nb = s.next_break(today)
    district = bool(s.auth) and s.cc == "US"
    noun = "break" if district else "school holiday"

    # answer first
    if nb:
        a, b = d(nb["start_date"]), d(nb["end_date"])
        n = (b - a).days + 1
        if a <= today:
            answer = f"School is out in {s.name} right now: {nb['name']} runs until {day_long(b)}."
        else:
            answer = f"The next {noun} in {s.name} is {nb['name']}, from {day_long(a)} to {day_long(b)}" + (f" ({n} days)." if n > 1 else ".")
    else:
        answer = f"Holibase has no upcoming school holidays for {s.name} yet."
    sys_label = " and ".join(school_year_label(y) for y in kept)
    lead2 = f"Below are all school holidays for the {sys_label} school year{'s' if len(kept) > 1 else ''}" if kept else ""
    if lead2:
        lead2 += ", with the first and last day of school where known, and the public holidays of the next twelve months."

    cal_by_year = {c["school_year"]: c for c in s.calendars}
    sections = []
    faq = []
    for sy, ps in kept.items():
        cal = cal_by_year.get(sy, {})
        rows = []
        for p in ps:
            a, b = d(p["start_date"]), d(p["end_date"])
            n = (b - a).days + 1
            past = b < today
            label = KIND.get(p["kind"], "No school")
            rows.append(
                f'<tr{" class=\"past\"" if past else ""}><td><b>{esc(p["name"])}</b>'
                + (f' <span class="pill pill-neutral">{esc(label)}</span>' if p["kind"] not in ("break", "holiday") else "")
                + f'</td><td class="num">{cell(a)}</td><td class="num">{cell(b)}</td><td class="num">{n}</td></tr>')
            if p["kind"] == "break" and not past and len(faq) < 5:
                faq.append((f"When is {p['name']} {a.year} in {s.name}?",
                            (f"{p['name']} {a.year} in {s.name} is from {day_long(a)} to {day_long(b)}, {n} days including weekends." if n > 1 else f"{p['name']} {a.year} in {s.name} is on {day_long(a)}.")))
        facts = []
        if cal.get("first_day"):
            facts.append(f"First day of school: <b>{esc(day(d(cal['first_day'])))}</b>")
            if d(cal["first_day"]) >= today:
                faq.append((f"When does school start in {s.name}?", f"The first day of school for {school_year_label(sy)} is {day_long(d(cal['first_day']))}."))
        if cal.get("last_day"):
            facts.append(f"Last day of school: <b>{esc(day(d(cal['last_day'])))}</b>")
            if d(cal["last_day"]) >= today:
                faq.append((f"When is the last day of school in {s.name}?", f"The last day of the {school_year_label(sy)} school year is {day_long(d(cal['last_day']))}."))
        sections.append(f"""<section class="gen-section">
<h2>School year {esc(school_year_label(sy))}</h2>
{('<p>' + ' · '.join(facts) + '</p>') if facts else ''}
<div class="table-scroll"><table class="data">
<thead><tr><th scope="col">Holiday</th><th scope="col">From</th><th scope="col">To</th><th scope="col">Days</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div>
</section>""")

    pub_rows = "".join(
        f'<tr><td class="num">{cell(d(h["date"]))}</td><td><b>{esc(h["name"])}</b>'
        + (f' <span class="muted">{esc(h["local_name"])}</span>' if h.get("local_name") and h["local_name"] != h["name"] else "")
        + (' <span class="pill pill-estimated">Estimated</span>' if h.get("is_estimated") else "")
        + (' <span class="pill pill-neutral">Observed</span>' if h.get("is_observed") and "observed" not in h["name"].lower() else "")
        + "</td></tr>" for h in s.public)
    region_label = s.region_name or s.country
    public_section = f"""<section class="gen-section">
<h2>Public holidays in {esc(region_label)}, next 12 months</h2>
<div class="table-scroll"><table class="data"><thead><tr><th scope="col">Date</th><th scope="col">Holiday</th></tr></thead>
<tbody>{pub_rows}</tbody></table></div>
<p class="body-s"><a href="/public-holidays/{s.cc.lower()}/">All public holidays in {esc(s.country)} →</a></p>
</section>""" if s.public else ""

    faq.append((f"Can I add the {s.name} school holidays to my calendar?",
                f"Yes. Subscribe to the free calendar feed {API}{s.feed_path()} in Apple Calendar, Google Calendar or Outlook. It updates by itself."))

    # sources
    src_rows = []
    for c in s.calendars:
        if c["school_year"] not in kept:
            continue
        origin = ORIGIN.get(c["origin"], c["origin"])
        url = c.get("source_url") or ("https://github.com/vacanza/holidays" if c["origin"] == "library" else None)
        link = f'<a href="{esc(url)}" rel="noopener nofollow">{esc(host(url))}</a>' if url else "–"
        retrieved = day(d(c["source_retrieved_at"])) if c.get("source_retrieved_at") else "–"
        src_rows.append(f'<tr><td class="num">{esc(school_year_label(c["school_year"]))}</td><td>{esc(origin)}</td><td>{link}</td><td class="num">{esc(retrieved)}</td></tr>')
        if c.get("notes") and c["origin"] == "official":
            src_rows.append(f'<tr><td></td><td colspan="3" class="body-s muted">{esc(c["notes"])}</td></tr>')

    sib = [x for x in siblings if x is not s]
    related = ""
    if sib:
        links = "".join(f'<a class="chip" href="{x.url}">{esc(x.name)}</a>' for x in sorted(sib, key=lambda x: x.name)[:40])
        related = f'<section class="gen-section"><h2>Other {"districts" if s.cc == "US" else "regions"} in {esc(s.country)}</h2><div class="chips">{links}</div></section>'

    crumbs = [("Home", "/"), ("School holidays", "/school-holidays/"), (s.country, f"/school-holidays/{s.cc.lower()}/")]
    if s.slug:
        crumbs.append((s.name, s.url))
    crumb_html, crumb_ld = breadcrumb(crumbs)
    faq_section, faq_ld = faq_html(faq)
    name_extra = f' <span class="muted">({esc(s.local_name)})</span>' if s.local_name else ""
    title = f"{s.name} school holidays {years}" if not district else f"{s.name} calendar {' and '.join(kept)}"
    desc = (f"{answer} All school holidays {years} for {s.name}" + (f", {s.where()}" if s.where() else "")
            + ", from the official calendar, with a free calendar feed.")
    body = f"""<section style="padding-bottom: 0"><div class="wrap gen">
{crumb_html}
<p class="overline">{'School district' if district else 'School holidays'} · {esc(s.where() or s.country)}</p>
<h1 class="h1">{esc(title)}{name_extra}</h1>
<p class="body-l answer">{esc(answer)}</p>
<p class="body-s muted">{esc(lead2)} Updated {esc(day(today))}.</p>
<div class="card subscribe-card"><h2 class="h3">Add to your calendar</h2>
<p class="body-s muted" style="margin: 4px 0 16px">Subscribe once; new dates and changes appear by themselves.</p>
<div class="subscribe">{subscribe_html("School holidays", s.feed_path(), f"School holidays {s.name}")}</div>
<p class="body-s" style="margin: 16px 0 0"><a href="{esc(s.app_url())}">Open in the interactive calendar →</a></p></div>
{''.join(sections)}
{public_section}
{faq_section}
<section class="gen-section"><h2>Sources</h2>
<div class="table-scroll"><table class="data"><thead><tr><th scope="col">School year</th><th scope="col">Source</th><th scope="col">Document</th><th scope="col">Checked</th></tr></thead>
<tbody>{''.join(src_rows) or '<tr><td colspan="4">–</td></tr>'}</tbody></table></div>
<p class="body-s subtle">Public holidays © python-holidays contributors (MIT). School calendars © Holibase contributors (CC BY 4.0). Schools can change their calendar; for important decisions, confirm with the school or authority. <a href="https://github.com/4Dgraphic/holibase/issues/new?title={urllib.parse.quote('Correction: ' + s.name)}">Report a mistake</a>.</p>
</section>
{related}
</div></section>"""
    return page(s.url, title, desc[:300], body, nav="calendar", ld=[crumb_ld, faq_ld], lastmod=today.isoformat())


def country_school_page(cc: str, group: list[Scope], today: dt.date) -> dict:
    country = country_name(cc)
    us = cc == "US"
    rows = []
    by_state = defaultdict(list)
    for s in group:
        by_state[s.region_name if us else ""].append(s)
    blocks = []
    for state in sorted(by_state):
        rows = []
        for s in sorted(by_state[state], key=lambda x: x.name):
            nb = s.next_break(today)
            when = esc(span(d(nb["start_date"]), d(nb["end_date"]))) if nb else "–"
            rows.append(f'<tr><td><a href="{s.url}"><b>{esc(s.name)}</b></a>'
                        + (f' <span class="muted">{esc(s.local_name)}</span>' if s.local_name else "")
                        + f'</td><td>{esc(nb["name"]) if nb else "–"}</td><td class="num">{when}</td></tr>')
        head = f"<h2>{esc(state)}</h2>" if state else ""
        blocks.append(f"""<section class="gen-section">{head}<div class="table-scroll"><table class="data">
<thead><tr><th scope="col">{'District' if us else 'Region'}</th><th scope="col">Next school holiday</th><th scope="col">Dates</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div></section>""")
    n = len(group)
    unit = "school districts" if us else "regions"
    crumb_html, crumb_ld = breadcrumb([("Home", "/"), ("School holidays", "/school-holidays/"), (country, f"/school-holidays/{cc.lower()}/")])
    title = f"School holidays in {country} {years_label([today, today.replace(year=today.year + 1)])}"
    intro = (f"School calendars for {n} of the largest US school districts, researched from each district's published calendar. "
             "Search all 19,000 districts in the interactive calendar.") if us else \
        f"School holidays for {n} {unit} of {country}, with the next holiday for each. Pick a region for all dates and a calendar feed."
    body = f"""<section style="padding-bottom: 0"><div class="wrap gen">
{crumb_html}
<p class="overline">School holidays</p>
<h1 class="h1">{esc(title)}</h1>
<p class="body-l answer">{esc(intro)}</p>
<p class="body-s"><a href="/calendar/">Search the interactive calendar →</a> · <a href="/public-holidays/{cc.lower()}/">Public holidays in {esc(country)} →</a></p>
{''.join(blocks)}
</div></section>"""
    desc = f"{title}: next holidays and full dates for {n} {unit}, with free calendar feeds for Apple, Google and Outlook."
    return page(f"/school-holidays/{cc.lower()}/", title, desc, body, nav="calendar", ld=[crumb_ld], lastmod=today.isoformat())


def school_index(by_cc: dict[str, list[Scope]], today: dt.date) -> dict:
    items = sorted(by_cc.items(), key=lambda kv: (-len(kv[1]), country_name(kv[0])))
    rows = "".join(
        f'<tr><td><a href="/school-holidays/{cc.lower()}/"><b>{esc(country_name(cc))}</b></a> <span class="pill pill-code">{cc}</span></td>'
        f'<td class="num">{len(g)}</td><td>{esc(", ".join(sorted({ORIGIN.get(c["origin"], c["origin"]) for s in g for c in s.calendars})))}</td></tr>'
        for cc, g in items)
    crumb_html, crumb_ld = breadcrumb([("Home", "/"), ("School holidays", "/school-holidays/")])
    n = sum(len(g) for g in by_cc.values())
    body = f"""<section style="padding-bottom: 0"><div class="wrap gen">
{crumb_html}
<p class="overline">School holidays</p>
<h1 class="h1">School holidays by country</h1>
<p class="body-l answer">School holiday calendars for {n} regions, zones and school districts in {len(by_cc)} countries, from official open data where it exists and researched calendars elsewhere.</p>
<section class="gen-section"><div class="table-scroll"><table class="data">
<thead><tr><th scope="col">Country</th><th scope="col">Calendars</th><th scope="col">Source</th></tr></thead>
<tbody>{rows}</tbody></table></div></section>
</div></section>"""
    return page("/school-holidays/", "School holidays by country", f"School holiday calendars for {n} regions and school districts in {len(by_cc)} countries, free as open data, API and calendar feeds.", body, nav="calendar", ld=[crumb_ld], lastmod=today.isoformat())


# ---------------------------------------------------------------- public holidays

def public_country_page(c: dict, school_ccs: set, today: dt.date) -> dict | None:
    cc = c["cc"]
    hs = c["holidays"]
    if not hs:
        return None
    country = country_name(cc)
    by_year = defaultdict(list)
    for h in hs:
        by_year[d(h["date"]).year].append(h)
    upcoming = [h for h in hs if d(h["date"]) >= today and not h.get("is_observed")]
    nxt = upcoming[0] if upcoming else None
    years = sorted(by_year)
    if nxt:
        answer = f"The next public holiday in {country} is {nxt['name']} on {day_long(d(nxt['date']))}."
    else:
        answer = f"Public holidays in {country} for {' and '.join(map(str, years))}."
    sections, faq = [], []
    for y in years:
        rows = "".join(
            f'<tr{" class=\"past\"" if d(h["date"]) < today else ""}><td class="num">{cell(d(h["date"]))}</td><td><b>{esc(h["name"])}</b>'
            + (f' <span class="muted">{esc(h["local_name"])}</span>' if h.get("local_name") and h["local_name"] != h["name"] else "")
            + (' <span class="pill pill-estimated">Estimated</span>' if h.get("is_estimated") else "")
            + (' <span class="pill pill-neutral">Observed</span>' if h.get("is_observed") and "observed" not in h["name"].lower() else "")
            + "</td></tr>" for h in by_year[y])
        count = len([h for h in by_year[y] if not h.get("is_observed")])
        sections.append(f"""<section class="gen-section"><h2>Public holidays in {esc(country)} {y}</h2>
<div class="table-scroll"><table class="data"><thead><tr><th scope="col">Date</th><th scope="col">Holiday</th></tr></thead>
<tbody>{rows}</tbody></table></div></section>""")
        faq.append((f"How many public holidays does {country} have in {y}?",
                    f"{country} has {count} nationwide public holidays in {y}" + (", plus regional holidays in some regions." if c.get("subdivisions") else ".")))
    if nxt:
        faq.insert(0, (f"When is the next public holiday in {country}?", answer))
    est = any(h.get("is_estimated") for h in hs)
    notes = []
    if c.get("subdivisions"):
        notes.append(f"These are the nationwide holidays. {country} has {c['subdivisions']} regions, some with extra holidays: "
                     f'<a href="/calendar/?country={cc}">pick a region in the interactive calendar</a>.')
    if est:
        notes.append("Dates marked Estimated depend on the sighting of the moon and can still move by a day or two.")
    crumb_html, crumb_ld = breadcrumb([("Home", "/"), ("Public holidays", "/public-holidays/"), (country, f"/public-holidays/{cc.lower()}/")])
    faq_section, faq_ld = faq_html(faq)
    title = f"Public holidays in {country} {' and '.join(map(str, years))}"
    school_link = f' · <a href="/school-holidays/{cc.lower()}/">School holidays in {esc(country)} →</a>' if cc in school_ccs else ""
    body = f"""<section style="padding-bottom: 0"><div class="wrap gen">
{crumb_html}
<p class="overline">Public holidays · {cc}</p>
<h1 class="h1">{esc(title)}</h1>
<p class="body-l answer">{esc(answer)}</p>
<p class="body-s muted">{' '.join(notes)} Updated {esc(day(today))}.</p>
<div class="card subscribe-card"><h2 class="h3">Add to your calendar</h2>
<div class="subscribe" style="margin-top: 12px">{subscribe_html(f"Public holidays {country}", f"/v1/public-holidays/{cc}.ics?lang=en", f"Public holidays {country}")}</div>
<p class="body-s" style="margin: 16px 0 0"><a href="/calendar/?country={cc}">Open in the interactive calendar →</a>{school_link}</p></div>
{''.join(sections)}
{faq_section}
<section class="gen-section"><h2>Source</h2>
<p class="body-s">Computed with <a href="https://github.com/vacanza/holidays" rel="noopener">python-holidays</a> (MIT), synced every week. Use the data in your own app with the free <a href="/docs/">Holibase API</a>: <code>GET {API}/v1/public-holidays/{cc}/{years[0]}</code>.</p>
</section>
</div></section>"""
    desc = f"{answer} All public holidays in {country} for {' and '.join(map(str, years))}, with local names and a free calendar feed."
    return page(f"/public-holidays/{cc.lower()}/", title, desc[:300], body, nav="coverage", ld=[crumb_ld, faq_ld], lastmod=today.isoformat())


def public_index(countries: list[str], today: dt.date) -> dict:
    chips = "".join(f'<a class="chip" href="/public-holidays/{cc.lower()}/">{esc(country_name(cc))}</a>'
                    for cc in sorted(countries, key=country_name))
    crumb_html, crumb_ld = breadcrumb([("Home", "/"), ("Public holidays", "/public-holidays/")])
    body = f"""<section style="padding-bottom: 0"><div class="wrap gen">
{crumb_html}
<p class="overline">Public holidays</p>
<h1 class="h1">Public holidays in {len(countries)} countries</h1>
<p class="body-l answer">Public holidays for {today.year} and {today.year + 1} in every country python-holidays supports, with local names and calendar feeds.</p>
<section class="gen-section"><div class="chips">{chips}</div></section>
</div></section>"""
    return page("/public-holidays/", f"Public holidays in {len(countries)} countries", f"Public holidays {today.year} and {today.year + 1} for {len(countries)} countries, free as open data, API and calendar feeds.", body, nav="coverage", ld=[crumb_ld], lastmod=today.isoformat())


# ---------------------------------------------------------------- entry point

def generate(snapshot: dict) -> tuple[list[dict], dict]:
    """Returns (pages, extras). extras: page map for the calendar app, coverage rows, llms.txt lines."""
    today = d(snapshot["today"])
    scopes = [Scope(r) for r in snapshot["scopes"]]
    scopes = [s for s in scopes if s.kept(today)]
    assign_slugs(scopes)
    by_cc = defaultdict(list)
    for s in scopes:
        by_cc[s.cc].append(s)

    pages = [school_index(by_cc, today)]
    for cc, group in by_cc.items():
        if len(group) == 1 and group[0].national:
            pages.append(scope_page(group[0], [], today))
        else:
            pages.append(country_school_page(cc, group, today))
            pages += [scope_page(s, group, today) for s in group]

    public_ccs = []
    for c in snapshot["public"]:
        p = public_country_page(c, set(by_cc), today)
        if p:
            pages.append(p)
            public_ccs.append(c["cc"])
    pages.append(public_index(public_ccs, today))

    page_map = {s.key: s.url for s in scopes}
    page_map.update({f"public:{cc}": f"/public-holidays/{cc.lower()}/" for cc in public_ccs})
    extras = {"page_map": page_map, "school_ccs": sorted(by_cc), "public_ccs": public_ccs,
              "scope_count": len(scopes), "coverage": snapshot.get("coverage")}
    return pages, extras


def coverage_rows(coverage: dict) -> str:
    """Server-rendered rows of the coverage table (coverage.js refreshes them live)."""
    out = []
    for x in coverage["school_holidays"]["by_country"]:
        cc = x["country_code"]
        name = x.get("name") or country_name(cc)
        level = ("School districts" if cc == "US" else "Local authorities and zones" if x["authorities"] and x["authorities"] == x["scopes"]
                 else "Regions and zones" if x["authorities"] else "States and regions" if x["scopes"] > 1 else "Nationwide")
        years = x["last_school_year"] if x["first_school_year"] == x["last_school_year"] else f'{x["first_school_year"]} to {x["last_school_year"]}'
        unver = x["scopes"] - x["scopes_verified"]
        out.append(f'<tr><td><a href="/school-holidays/{cc.lower()}/">{esc(name)}</a> <span class="pill pill-code">{cc}</span></td>'
                   f'<td>{level}</td><td class="num">{x["scopes_verified"]:,}</td><td class="num muted">{f"{unver:,}" if unver else "–"}</td>'
                   f'<td class="num">{esc(years)}</td><td>{esc(", ".join(ORIGIN.get(o, o) for o in x["origins"]))}</td></tr>')
    return "".join(out)


def stats(coverage: dict) -> dict:
    """Values for data-stat spans baked into the static pages."""
    ph, sh, us = coverage["public_holidays"], coverage["school_holidays"], coverage["us_districts"]
    compact = lambda n: f"{n / 1e6:.1f}M" if n >= 1e6 else f"{round(n / 1e3)}k" if n >= 1e4 else f"{n:,}"  # noqa: E731
    out = {
        "ph-countries": f'{ph["countries"]:,}', "ph-subdivisions": f'{ph["subdivisions"]:,}',
        "ph-first-year": ph["first_date"][:4], "ph-last-year": ph["last_date"][:4],
        "sh-countries": f'{sh["countries"]:,}', "sh-calendars": f'{sh["calendars"]:,}',
        "sh-scopes": f'{sum(x["scopes_verified"] for x in sh["by_country"]):,}',
        "us-directory": f'{us["directory"]:,}', "us-verified": f'{us["verified"]:,}',
    }
    if us.get("students"):
        out["us-students-pct"] = f'{100 * us["students_verified"] / us["students"]:.1f}%'
        out["us-students"] = compact(us["students_verified"])
        out["us-students-all"] = compact(us["students"])
    return out


def json_dumps(x) -> str:
    return json.dumps(x, ensure_ascii=False, separators=(",", ":"))
