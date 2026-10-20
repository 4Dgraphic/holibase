"""
Static pages generated from web/.cache/snapshot.json (see snapshot.py), in English and, for the
countries where it matters, German, French, Dutch, Spanish, Italian, Polish, Portuguese, Czech, Slovak and
Romanian (texts in i18n.py and i18n_more.py), plus a home page per language (/de/, /es/, ...):

    /school-holidays/  /school-holidays/{cc}/  /school-holidays/{cc}/{region}/
    /public-holidays/  /public-holidays/{cc}/
    /de/schulferien/deutschland/niedersachsen/   /de/feiertage/deutschland/
    /fr/vacances-scolaires/france/zone-a/        /fr/jours-feries/france/
    /nl/schoolvakanties/nederland/regio-noord/   /nl/feestdagen/nederland/

Every page carries its dates in the HTML, so search engines and AI crawlers can read them without
running JavaScript, and links its language versions with hreflang. Nothing here talks to the network.
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
from babel.dates import format_date

from i18n import DATE, LANG_NAMES, LANGS, PATHS, REGION, T, in_country

API = "https://api.holibase.org"
SITE = "https://holibase.org"
TERRITORIES = {lang: Locale(lang).territories for lang in LANGS}

esc = lambda s: html.escape(str(s if s is not None else ""), quote=True)  # noqa: E731


def d(s: str) -> dt.date:
    return dt.date.fromisoformat(s[:10])


def slugify(s: str, lang: str = "en") -> str:
    s = s.replace("ß", "ss")
    for a, b in (("ł", "l"), ("Ł", "L"), ("đ", "d"), ("Đ", "D"), ("ø", "o"), ("Ø", "O"), ("æ", "ae"), ("œ", "oe")):
        s = s.replace(a, b)
    if lang == "de":
        for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("Ä", "Ae"), ("Ö", "Oe"), ("Ü", "Ue")):
            s = s.replace(a, b)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "x"


def country_name(cc: str, lang: str = "en") -> str:
    return TERRITORIES[lang].get(cc, cc)


def host(url: str | None) -> str:
    return (urllib.parse.urlparse(url).hostname or "") if url else ""


class Loc:
    """Formatting and texts for one language."""

    def __init__(self, lang: str):
        self.lang = lang
        self.p_short, self.p_long, self.p_noyear = DATE[lang]

    def t(self, key: str, **kw) -> str:
        return T[self.lang][key].format(**kw)

    def day(self, x: dt.date) -> str:
        return format_date(x, self.p_short, locale=self.lang)

    def day_long(self, x: dt.date) -> str:
        return format_date(x, self.p_long, locale=self.lang)

    def cell(self, x: dt.date) -> str:
        """Table date; the weekday is hidden on narrow screens."""
        wd = format_date(x, "EEE", locale=self.lang)
        rest = self.day(x)
        rest = rest[len(wd):].lstrip(", ") if rest.startswith(wd) else rest
        return f'<span class="wd">{esc(wd)}{"," if self.lang == "de" else ""} </span>{esc(rest)}'

    def span(self, a: dt.date, b: dt.date) -> str:
        if a == b:
            return self.day(a)
        first = format_date(a, self.p_noyear, locale=self.lang) if a.year == b.year else self.day(a)
        return f"{first} – {self.day(b)}"

    def sy(self, school_year: str) -> str:
        if self.t("sy_sep") == "-" and re.fullmatch(r"\d{4}-\d{2}", school_year):
            return f"{school_year[:4]}-{school_year[:2]}{school_year[5:]}"  # 2026-27 -> 2026-2027
        return school_year.replace("-", self.t("sy_sep"))

    def years(self, dates: list[dt.date]) -> str:
        ys = sorted({x.year for x in dates})[:2]
        return f" {self.t('and')} ".join(str(y) for y in ys)

    def country(self, cc: str) -> str:
        return country_name(cc, self.lang)

    def in_country(self, cc: str) -> str:
        return in_country(self.lang, cc, self.country(cc))

    @property
    def colon(self) -> str:
        return "\u202f:" if self.lang == "fr" else ":"

    def origin(self, o: str) -> str:
        key = f"origin_{o}"
        return self.t(key) if key in T[self.lang] else o

    def source(self, cal: dict) -> str:
        """Label for a calendar's source: OpenHolidays is named, other origins by their kind."""
        if cal.get("source_id") == "openholidays":
            return "OpenHolidays (ODbL)"
        return self.origin(cal["origin"])


# ---------------------------------------------------------------- URLs

def home_url(lang):
    return PATHS[lang]["prefix"] + "/"


def school_index_url(lang):
    p = PATHS[lang]
    return f"{p['prefix']}/{p['school']}/"


def public_index_url(lang):
    p = PATHS[lang]
    return f"{p['prefix']}/{p['public']}/"


def school_country_url(lang, cc):
    seg = cc.lower() if lang == "en" else slugify(country_name(cc, lang), lang)
    return f"{school_index_url(lang)}{seg}/"


def public_country_url(lang, cc):
    seg = cc.lower() if lang == "en" else slugify(country_name(cc, lang), lang)
    return f"{public_index_url(lang)}{seg}/"


# ---------------------------------------------------------------- shared blocks

def feed_links(path: str, name: str) -> dict:
    https = API + path
    webcal = "webcal:" + https[len("https:"):]
    return {
        "https": https, "apple": webcal,
        "google": "https://calendar.google.com/calendar/render?cid=" + urllib.parse.quote(webcal, safe=""),
        "outlook": "https://outlook.live.com/calendar/0/addfromweb?url=" + urllib.parse.quote(https, safe="")
                   + "&name=" + urllib.parse.quote(name, safe=""),
    }


def subscribe_html(L: Loc, label: str, path: str, name: str) -> str:
    f = feed_links(path, name)
    return f"""<div><p class="body-s muted" style="margin: 0 0 8px">{esc(label)}</p>
<div class="row">
<a class="btn btn-primary btn-sm" href="{esc(f['apple'])}">Apple Calendar</a>
<a class="btn btn-secondary btn-sm" href="{esc(f['google'])}" rel="noopener" target="_blank">Google Calendar</a>
<a class="btn btn-secondary btn-sm" href="{esc(f['outlook'])}" rel="noopener" target="_blank">Outlook</a>
<a class="btn btn-secondary btn-sm" href="{esc(f['https'])}" download>{esc(L.t('download'))}</a>
</div></div>"""


def breadcrumb(items: list[tuple[str, str]]) -> tuple[str, dict]:
    links = ' <span aria-hidden="true">/</span> '.join(
        f'<a href="{esc(p)}">{esc(n)}</a>' if i < len(items) - 1 else f'<span aria-current="page">{esc(n)}</span>'
        for i, (n, p) in enumerate(items))
    ld = {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": i + 1, "name": n, "item": SITE + p} for i, (n, p) in enumerate(items)]}
    return f'<nav class="crumbs" aria-label="Breadcrumb">{links}</nav>', ld


def faq_html(L: Loc, faq: list[tuple[str, str]]) -> tuple[str, dict | None]:
    if not faq:
        return "", None
    body = "".join(f"<h3>{esc(q)}</h3><p>{esc(a)}</p>" for q, a in faq)
    ld = {"@context": "https://schema.org", "@type": "FAQPage", "inLanguage": L.lang, "mainEntity": [
        {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]}
    return f'<section class="gen-section"><h2>{esc(L.t("faq"))}</h2>{body}</section>', ld


def holiday_rows(L: Loc, hs: list[dict], today: dt.date, mark_past: bool) -> str:
    out = []
    for h in hs:
        x = d(h["date"])
        past = mark_past and x < today
        extra = ""
        if h.get("local_name") and h["local_name"] != h["name"]:
            extra += f' <span class="muted">{esc(h["local_name"])}</span>'
        if h.get("is_estimated"):
            extra += f' <span class="pill pill-estimated">{esc(L.t("estimated"))}</span>'
        if h.get("is_observed") and "observ" not in h["name"].lower():
            extra += f' <span class="pill pill-neutral">{esc(L.t("observed"))}</span>'
        out.append(f'<tr{" class=\"past\"" if past else ""}><td class="num">{L.cell(x)}</td><td><b>{esc(h["name"])}</b>{extra}</td></tr>')
    return "".join(out)


def page(lang, path, title, description, body, nav="", ld=(), lastmod=None, group=None, meta_title=None):
    return {"lang": lang, "path": path, "title": meta_title or title, "description": description, "body": body, "nav": nav,
            "ld": [x for x in ld if x], "theme": "dark", "lastmod": lastmod, "group": group, "no_brand": bool(meta_title)}


def lang_switch_placeholder() -> str:
    return "<!--langs-->"


# ---------------------------------------------------------------- school holidays

class Scope:
    def __init__(self, raw: dict):
        self.raw = raw
        self.cc = raw["cc"]
        self.sub = raw.get("sub")
        self.auth = raw.get("auth")
        self.region = self.sub or raw.get("auth_sub")
        self.national = not self.sub and not self.auth
        self.calendars = [c for c in raw["calendars"] if c["status"] == "confirmed"]
        self.langs = ["en"] + [l for l in (raw.get("l10n") or {}) if l in LANGS and l != "en"]
        self.slug = {}
        self.key = f"auth:{self.auth}" if self.auth else (self.sub or self.cc)

    def periods(self, lang):
        src = self.raw["periods"] if lang == "en" else self.raw["l10n"][lang]["periods"]
        return [p for p in src if p["status"] == "confirmed"]

    def public(self, lang):
        return (self.raw.get("public") if lang == "en" else self.raw["l10n"][lang]["public"]) or []

    def region_name(self, lang):
        stored = self.raw.get("sub_name") or ""
        name = REGION[lang].get(self.region)
        if not name:
            name = stored
        if re.fullmatch(r"[A-Z]{2}", name or ""):
            name = country_name(name, lang)
        return name or ""

    def name(self, lang):
        return self.raw.get("auth_name") or (self.region_name(lang) if self.sub else country_name(self.cc, lang))

    def local_name(self, lang):
        """The stored local name, shown next to a translated name (Lower Saxony (Niedersachsen))."""
        stored = self.raw.get("sub_name")
        if self.sub and stored and stored != self.name(lang) and not re.fullmatch(r"[A-Z]{2}", stored):
            return stored
        return None

    def url(self, lang):
        base = school_country_url(lang, self.cc)
        return base + (f"{self.slug[lang]}/" if self.slug.get(lang) else "")

    def kept(self, today: dt.date, lang="en"):
        by_year = defaultdict(list)
        for p in self.periods(lang):
            by_year[p["school_year"]].append(p)
        years = [y for y, ps in by_year.items() if max(d(p["end_date"]) for p in ps) >= today]
        return {y: sorted(by_year[y], key=lambda p: p["start_date"]) for y in sorted(years)}

    def next_break(self, today: dt.date, lang="en"):
        upcoming = [p for p in self.periods(lang) if d(p["end_date"]) >= today and p["kind"] != "early_release"]
        breaks = [p for p in upcoming if p["kind"] == "break"]
        return (breaks or upcoming or [None])[0]

    def feed_path(self, lang):
        q = f"authority={self.auth}&" if self.auth else f"subdivision={self.sub}&" if self.sub else ""
        return f"/v1/school-holidays/{self.cc}.ics?{q}lang={lang}"

    def app_url(self):
        q = {"country": self.cc}
        if self.auth:
            q["authority"] = self.auth
        elif self.sub:
            q["subdivision"] = self.sub
        return "/calendar/?" + urllib.parse.urlencode(q)

    def where(self, lang):
        parts = [self.raw.get("auth_city"), self.region_name(lang) if self.auth else None, country_name(self.cc, lang)]
        return ", ".join(p for p in parts if p and p != self.name(lang))


def assign_slugs(scopes: list[Scope]) -> None:
    by_cc = defaultdict(list)
    for s in scopes:
        by_cc[s.cc].append(s)
    for cc, group in by_cc.items():
        if len(group) == 1 and group[0].national:
            continue  # the country page is the calendar
        for lang in LANGS:
            seen = set()
            for s in sorted((s for s in group if lang in s.langs), key=lambda s: (s.national, s.name(lang))):
                base = "nationwide" if s.national else slugify(s.name(lang), lang)
                slug = base
                if slug in seen:
                    slug = f"{base}-{slugify(s.raw.get('auth_city') or s.region_name(lang) or '')}".strip("-")
                if slug in seen:
                    slug = f"{base}-{str(s.auth)[:6]}"
                seen.add(slug)
                s.slug[lang] = slug


def scope_page(s: Scope, siblings: list[Scope], today: dt.date, lang: str, public_langs: dict) -> dict:
    L = Loc(lang)
    name = s.name(lang)
    kept = s.kept(today, lang)
    all_kept = [p for ps in kept.values() for p in ps]
    years = L.years([d(p["start_date"]) for p in all_kept] or [today])
    nb = s.next_break(today, lang)
    district = bool(s.auth) and s.cc == "US"

    if nb:
        a, b = d(nb["start_date"]), d(nb["end_date"])
        n = (b - a).days + 1
        if a <= today:
            answer = L.t("ongoing", name=name, holiday=nb["name"], end=L.day_long(b))
        else:
            answer = L.t("next_district" if district else "next", name=name, holiday=nb["name"],
                         start=L.day_long(a), end=L.day_long(b), days=L.t("days_paren", n=n) if n > 1 else "")
    else:
        answer = L.t("none", name=name)
    sy_list = f" {L.t('and')} ".join(L.sy(y) for y in kept)
    lead2 = L.t("lead_many" if len(kept) > 1 else "lead_one", sy=sy_list) if kept else ""

    cal_by_year = {c["school_year"]: c for c in s.calendars}
    sections, faq = [], []
    for sy, ps in kept.items():
        cal = cal_by_year.get(sy, {})
        rows = []
        for p in ps:
            a, b = d(p["start_date"]), d(p["end_date"])
            n = (b - a).days + 1
            past = b < today
            kind = p["kind"] if f"kind_{p['kind']}" in T[lang] else "other"
            pill = f' <span class="pill pill-neutral">{esc(L.t("kind_" + kind))}</span>' if kind not in ("break", "holiday") else ""
            rows.append(f'<tr{" class=\"past\"" if past else ""}><td><b>{esc(p["name"])}</b>{pill}</td>'
                        f'<td class="num">{L.cell(a)}</td><td class="num">{L.cell(b)}</td><td class="num">{n}</td></tr>')
            if p["kind"] == "break" and not past and len(faq) < 5:
                if n > 1:
                    faq.append((L.t("q_when", holiday=p["name"], year=a.year, name=name),
                                L.t("a_when", holiday=p["name"], year=a.year, name=name, start=L.day_long(a), end=L.day_long(b), n=n)))
                else:
                    faq.append((L.t("q_when", holiday=p["name"], year=a.year, name=name),
                                L.t("a_when1", holiday=p["name"], year=a.year, name=name, start=L.day_long(a))))
        facts = []
        if cal.get("first_day"):
            fd = d(cal["first_day"])
            facts.append(f"{esc(L.t('first_day'))}{L.colon} <b>{esc(L.day(fd))}</b>")
            if fd >= today:
                faq.append((L.t("q_start", name=name), L.t("a_start", sy=L.sy(sy), date=L.day_long(fd))))
        if cal.get("last_day"):
            ld_ = d(cal["last_day"])
            facts.append(f"{esc(L.t('last_day'))}{L.colon} <b>{esc(L.day(ld_))}</b>")
            if ld_ >= today:
                faq.append((L.t("q_last", name=name), L.t("a_last", sy=L.sy(sy), date=L.day_long(ld_))))
        sections.append(f"""<section class="gen-section">
<h2>{esc(L.t('school_year', sy=L.sy(sy)))}</h2>
{('<p>' + ' · '.join(facts) + '</p>') if facts else ''}
<div class="table-scroll"><table class="data">
<thead><tr><th scope="col">{esc(L.t('th_holiday'))}</th><th scope="col">{esc(L.t('th_from'))}</th><th scope="col">{esc(L.t('th_to'))}</th><th scope="col">{esc(L.t('th_days'))}</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div>
</section>""")

    pub = s.public(lang)
    region_label = s.region_name(lang) or L.country(s.cc)
    pub_lang = lang if lang in public_langs.get(s.cc, []) else "en"
    public_section = f"""<section class="gen-section">
<h2>{esc(L.t('public_next12', region=region_label))}</h2>
<div class="table-scroll"><table class="data"><thead><tr><th scope="col">{esc(L.t('th_date'))}</th><th scope="col">{esc(L.t('th_public'))}</th></tr></thead>
<tbody>{holiday_rows(L, pub, today, False)}</tbody></table></div>
<p class="body-s"><a href="{public_country_url(pub_lang, s.cc)}">{esc(L.t('all_public', in_country=L.in_country(s.cc)))}</a></p>
</section>""" if pub else ""

    faq.append((L.t("q_feed", name=name), L.t("a_feed", url=API + s.feed_path(lang))))
    faq.append((L.t("q_iphone", name=name), L.t("a_iphone")))
    faq.append((L.t("q_google", name=name), L.t("a_google")))

    src_rows = []
    for c in s.calendars:
        if c["school_year"] not in kept:
            continue
        url = c.get("source_url") or ("https://github.com/vacanza/holidays" if c["origin"] == "library" else None)
        link = f'<a href="{esc(url)}" rel="noopener nofollow">{esc(host(url))}</a>' if url else "–"
        checked = L.day(d(c["source_retrieved_at"])) if c.get("source_retrieved_at") else "–"
        src_rows.append(f'<tr><td class="num">{esc(L.sy(c["school_year"]))}</td><td>{esc(L.source(c))}</td><td>{link}</td><td class="num">{esc(checked)}</td></tr>')
        if c.get("notes") and c["origin"] == "official":
            src_rows.append(f'<tr><td></td><td colspan="3" class="body-s muted">{esc(c["notes"])}</td></tr>')

    sib = [x for x in siblings if x is not s and lang in x.langs]
    related = ""
    if sib:
        links = "".join(f'<a class="chip" href="{x.url(lang)}">{esc(x.name(lang))}</a>' for x in sorted(sib, key=lambda x: x.name(lang))[:40])
        heading = L.t("other_districts" if s.cc == "US" else "other_regions", in_country=L.in_country(s.cc))
        related = f'<section class="gen-section"><h2>{esc(heading)}</h2><div class="chips">{links}</div></section>'

    crumbs = [(L.t("home"), home_url(lang)), (L.t("school_holidays"), school_index_url(lang)), (L.country(s.cc), school_country_url(lang, s.cc))]
    if s.slug.get(lang):
        crumbs.append((name, s.url(lang)))
    crumb_html, crumb_ld = breadcrumb(crumbs)
    faq_section, faq_ld = faq_html(L, faq)
    local = s.local_name(lang)
    name_extra = f' <span class="muted">({esc(local)})</span>' if local else ""
    title = L.t("title_district", name=name, sy=f" {L.t('and')} ".join(L.sy(y) for y in kept)) if district else L.t("title_scope", name=name, years=years)
    where = s.where(lang) or L.country(s.cc)
    overline = L.t("overline_district" if district else "overline_scope", where=where)
    desc = L.t("desc_scope", answer=answer, years=years, name=name)
    oh_credit = " " + esc(L.t("attribution_oh")) if any(c.get("source_id") == "openholidays" and c["school_year"] in kept for c in s.calendars) else ""
    report = "/submit/?" + urllib.parse.urlencode({"country": s.cc, **({"authority": s.auth} if s.auth else {"subdivision": s.sub} if s.sub else {}), "lang": lang})
    body = f"""<section style="padding-bottom: 0"><div class="wrap gen">
{crumb_html}
<p class="overline">{esc(overline)}</p>
<h1 class="h1">{esc(title)}{name_extra}</h1>
<p class="body-l answer">{esc(answer)}</p>
<p class="body-s muted">{esc(lead2)} {esc(L.t('updated', date=L.day(today)))}</p>
<!--langs-->
<div class="card subscribe-card"><h2 class="h3">{esc(L.t('add_title'))}</h2>
<p class="body-s muted" style="margin: 4px 0 16px">{esc(L.t('add_desc'))}</p>
<div class="subscribe">{subscribe_html(L, L.t('feed_school'), s.feed_path(lang), f"{L.t('school_holidays')} {name}")}</div>
<p class="body-s" style="margin: 16px 0 0"><a href="{esc(s.app_url())}">{esc(L.t('open_app'))}</a></p></div>
{''.join(sections)}
{public_section}
{faq_section}
<section class="gen-section"><h2>{esc(L.t('sources'))}</h2>
<div class="table-scroll"><table class="data"><thead><tr><th scope="col">{esc(L.t('th_sy'))}</th><th scope="col">{esc(L.t('th_source'))}</th><th scope="col">{esc(L.t('th_doc'))}</th><th scope="col">{esc(L.t('th_checked'))}</th></tr></thead>
<tbody>{''.join(src_rows) or '<tr><td colspan="4">–</td></tr>'}</tbody></table></div>
<p class="body-s subtle">{esc(L.t('attribution'))}{oh_credit} <a href="{esc(report)}">{esc(L.t('report'))}</a>.</p>
</section>
{related}
</div></section>"""
    return page(lang, s.url(lang), title, desc[:300], body, nav="calendar", ld=[crumb_ld, faq_ld],
                lastmod=today.isoformat(), group=f"school:{s.key}", meta_title=title + L.t("seo_suffix"))


def country_school_page(cc: str, group: list[Scope], today: dt.date, lang: str, public_langs: dict) -> dict:
    L = Loc(lang)
    us = cc == "US"
    group = [s for s in group if lang in s.langs]
    by_state = defaultdict(list)
    for s in group:
        by_state[s.region_name(lang) if us else ""].append(s)
    blocks = []
    for state in sorted(by_state):
        rows = []
        for s in sorted(by_state[state], key=lambda x: x.name(lang)):
            nb = s.next_break(today, lang)
            when = esc(L.span(d(nb["start_date"]), d(nb["end_date"]))) if nb else "–"
            local = s.local_name(lang)
            rows.append(f'<tr><td><a href="{s.url(lang)}"><b>{esc(s.name(lang))}</b></a>'
                        + (f' <span class="muted">{esc(local)}</span>' if local else "")
                        + f'</td><td>{esc(nb["name"]) if nb else "–"}</td><td class="num">{when}</td></tr>')
        head = f"<h2>{esc(state)}</h2>" if state else ""
        blocks.append(f"""<section class="gen-section">{head}<div class="table-scroll"><table class="data">
<thead><tr><th scope="col">{esc(L.t('th_district' if us else 'th_region'))}</th><th scope="col">{esc(L.t('th_next'))}</th><th scope="col">{esc(L.t('th_dates'))}</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div></section>""")
    n = len(group)
    url = school_country_url(lang, cc)
    crumb_html, crumb_ld = breadcrumb([(L.t("home"), home_url(lang)), (L.t("school_holidays"), school_index_url(lang)), (L.country(cc), url)])
    title = L.t("hub_title", in_country=L.in_country(cc), years=L.years([today, today.replace(year=today.year + 1)]))
    intro = L.t("hub_intro_us" if us else "hub_intro", n=n, in_country=L.in_country(cc))
    pub_lang = lang if lang in public_langs.get(cc, []) else "en"
    body = f"""<section style="padding-bottom: 0"><div class="wrap gen">
{crumb_html}
<p class="overline">{esc(L.t('school_holidays'))}</p>
<h1 class="h1">{esc(title)}</h1>
<p class="body-l answer">{esc(intro)}</p>
<!--langs-->
<p class="body-s"><a href="/calendar/">{esc(L.t('search_link'))}</a> · <a href="{public_country_url(pub_lang, cc)}">{esc(L.t('public_link', in_country=L.in_country(cc)))}</a></p>
{''.join(blocks)}
</div></section>"""
    return page(lang, url, title, L.t("hub_desc", title=title, n=n), body, nav="calendar", ld=[crumb_ld], meta_title=title + L.t("seo_suffix"),
                lastmod=today.isoformat(), group=f"school-country:{cc}")


def school_index(by_cc: dict[str, list[Scope]], today: dt.date, lang: str) -> dict:
    L = Loc(lang)
    items = [(cc, [s for s in g if lang in s.langs]) for cc, g in by_cc.items()]
    items = sorted([x for x in items if x[1]], key=lambda kv: (-len(kv[1]), L.country(kv[0])))
    rows = "".join(
        f'<tr><td><a href="{school_country_url(lang, cc)}"><b>{esc(L.country(cc))}</b></a> <span class="pill pill-code">{cc}</span></td>'
        f'<td class="num">{len(g)}</td><td>{esc(", ".join(sorted({L.source(c) for s in g for c in s.calendars})))}</td></tr>'
        for cc, g in items)
    crumb_html, crumb_ld = breadcrumb([(L.t("home"), home_url(lang)), (L.t("school_holidays"), school_index_url(lang))])
    n = sum(len(g) for _, g in items)
    more = f'<p class="body-s"><a href="{school_index_url("en")}">{esc(L.t("all_countries"))}</a></p>' if lang != "en" else ""
    body = f"""<section style="padding-bottom: 0"><div class="wrap gen">
{crumb_html}
<p class="overline">{esc(L.t('school_holidays'))}</p>
<h1 class="h1">{esc(L.t('index_title'))}</h1>
<p class="body-l answer">{esc(L.t('index_intro', n=n, c=len(items)))}</p>
<!--langs-->
<section class="gen-section"><div class="table-scroll"><table class="data">
<thead><tr><th scope="col">{esc(L.t('th_country'))}</th><th scope="col">{esc(L.t('th_calendars'))}</th><th scope="col">{esc(L.t('th_source'))}</th></tr></thead>
<tbody>{rows}</tbody></table></div>{more}</section>
</div></section>"""
    return page(lang, school_index_url(lang), L.t("index_title"), L.t("index_desc", n=n, c=len(items)), body,
                nav="calendar", ld=[crumb_ld], lastmod=today.isoformat(), group="school-index")


# ---------------------------------------------------------------- public holidays

def public_country_page(c: dict, school_urls: dict, today: dt.date, lang: str) -> dict | None:
    L = Loc(lang)
    cc = c["cc"]
    hs = c["holidays"] if lang == "en" else (c.get("l10n") or {}).get(lang) or []
    if not hs:
        return None
    by_year = defaultdict(list)
    for h in hs:
        by_year[d(h["date"]).year].append(h)
    upcoming = [h for h in hs if d(h["date"]) >= today and not h.get("is_observed")]
    nxt = upcoming[0] if upcoming else None
    years = sorted(by_year)
    years_s = f" {L.t('and')} ".join(map(str, years))
    inc = L.in_country(cc)
    answer = (L.t("pub_answer", in_country=inc, holiday=nxt["name"], date=L.day_long(d(nxt["date"]))) if nxt
              else L.t("pub_answer_none", in_country=inc, years=years_s))
    sections, faq = [], []
    for y in years:
        count = len([h for h in by_year[y] if not h.get("is_observed")])
        sections.append(f"""<section class="gen-section"><h2>{esc(L.t('pub_year', in_country=inc, year=y))}</h2>
<div class="table-scroll"><table class="data"><thead><tr><th scope="col">{esc(L.t('th_date'))}</th><th scope="col">{esc(L.t('th_public'))}</th></tr></thead>
<tbody>{holiday_rows(L, by_year[y], today, True)}</tbody></table></div></section>""")
        extra = L.t("a_count_extra") if c.get("subdivisions") else ""
        faq.append((L.t("q_count", country=L.country(cc), in_country=inc, year=y),
                    L.t("a_count", country=L.country(cc), In_country=inc[:1].upper() + inc[1:], n=count, year=y, extra=extra)))
    if nxt:
        faq.insert(0, (L.t("q_next", in_country=inc), answer))
    notes = []
    if c.get("subdivisions"):
        notes.append(L.t("note_regions", country=esc(L.country(cc)), n=c["subdivisions"], url=f"/calendar/?country={cc}"))
    if any(h.get("is_estimated") for h in hs):
        notes.append(esc(L.t("note_est")))
    url = public_country_url(lang, cc)
    crumb_html, crumb_ld = breadcrumb([(L.t("home"), home_url(lang)), (L.t("public_holidays"), public_index_url(lang)), (L.country(cc), url)])
    faq_section, faq_ld = faq_html(L, faq)
    title = L.t("pub_title", in_country=inc, years=years_s)
    school_url = school_urls.get((lang, cc)) or school_urls.get(("en", cc))
    school_link = f' · <a href="{school_url}">{esc(L.t("school_link", in_country=inc))}</a>' if school_url else ""
    body = f"""<section style="padding-bottom: 0"><div class="wrap gen">
{crumb_html}
<p class="overline">{esc(L.t('public_holidays'))} · {cc}</p>
<h1 class="h1">{esc(title)}</h1>
<p class="body-l answer">{esc(answer)}</p>
<p class="body-s muted">{' '.join(notes)} {esc(L.t('updated', date=L.day(today)))}</p>
<!--langs-->
<div class="card subscribe-card"><h2 class="h3">{esc(L.t('add_title'))}</h2>
<div class="subscribe" style="margin-top: 12px">{subscribe_html(L, L.t('feed_public', country=L.country(cc)), f"/v1/public-holidays/{cc}.ics?lang={lang}", L.t('feed_public', country=L.country(cc)))}</div>
<p class="body-s" style="margin: 16px 0 0"><a href="/calendar/?country={cc}">{esc(L.t('open_app'))}</a>{school_link}</p></div>
{''.join(sections)}
{faq_section}
<section class="gen-section"><h2>{esc(L.t('source'))}</h2>
<p class="body-s">{L.t('source_public')} <code>GET {API}/v1/public-holidays/{cc}/{years[0]}</code></p>
</section>
</div></section>"""
    return page(lang, url, title, L.t("desc_public", answer=answer, in_country=inc, years=years_s)[:300], body,
                nav="coverage", ld=[crumb_ld, faq_ld], lastmod=today.isoformat(), group=f"public:{cc}")


def public_index(countries: list[str], today: dt.date, lang: str) -> dict:
    L = Loc(lang)
    chips = "".join(f'<a class="chip" href="{public_country_url(lang, cc)}">{esc(L.country(cc))}</a>'
                    for cc in sorted(countries, key=L.country))
    crumb_html, crumb_ld = breadcrumb([(L.t("home"), home_url(lang)), (L.t("public_holidays"), public_index_url(lang))])
    title = L.t("pub_index_title", n=len(countries))
    more = f'<p class="body-s"><a href="{public_index_url("en")}">{esc(L.t("all_countries"))}</a></p>' if lang != "en" else ""
    body = f"""<section style="padding-bottom: 0"><div class="wrap gen">
{crumb_html}
<p class="overline">{esc(L.t('public_holidays'))}</p>
<h1 class="h1">{esc(title)}</h1>
<p class="body-l answer">{esc(L.t('pub_index_intro', y0=today.year, y1=today.year + 1))}</p>
<!--langs-->
<section class="gen-section"><div class="chips">{chips}</div>{more}</section>
</div></section>"""
    return page(lang, public_index_url(lang), title, L.t("pub_index_desc", y0=today.year, y1=today.year + 1, n=len(countries)),
                body, nav="coverage", ld=[crumb_ld], lastmod=today.isoformat(), group="public-index")


# ---------------------------------------------------------------- localized home pages

# Countries a language's home page lists first (then the rest by number of calendars).
HOME_FIRST = {"de": ["DE", "AT", "CH", "LI", "LU"], "fr": ["FR", "BE", "CH", "LU"], "nl": ["NL", "BE"],
              "es": ["ES", "MX"], "it": ["IT", "CH", "SM"], "pl": ["PL"], "pt": ["PT"], "cs": ["CZ"], "sk": ["SK"],
              "ro": ["RO", "MD"]}


def home_page(lang: str, by_cc: dict[str, list[Scope]], public_ccs: list[str], today: dt.date) -> dict | None:
    """A home page for parents in their language: subscribe to the school holidays of a region."""
    L = Loc(lang)
    groups = {cc: [s for s in g if lang in s.langs] for cc, g in by_cc.items()}
    groups = {cc: g for cc, g in groups.items() if g}
    if not groups:
        return None
    first = HOME_FIRST.get(lang, [])
    order = sorted(groups, key=lambda cc: (first.index(cc) if cc in first else len(first), -len(groups[cc]), L.country(cc)))
    cards = []
    for cc in order:
        g = sorted(groups[cc], key=lambda s: s.name(lang))
        national = len(g) == 1 and g[0].national
        chips = "" if national else "".join(
            f'<a class="chip" href="{s.url(lang)}">{esc(s.name(lang))}</a>' for s in g[:48])
        links = [] if national else [(school_country_url(lang, cc), L.t("home_all_regions", in_country=L.in_country(cc)))]
        if cc in public_ccs:
            links.append((public_country_url(lang, cc), L.t("home_public_link", in_country=L.in_country(cc))))
        more = ('<p class="body-s" style="margin: 16px 0 0">'
                + " · ".join(f'<a class="link-arrow" href="{u}">{esc(t)}</a>' for u, t in links) + "</p>") if links else ""
        cards.append(f"""<article class="card card-lg home-country">
<h3 class="h2"><a href="{school_country_url(lang, cc)}">{esc(L.t('title_scope', name=L.country(cc), years='').strip()) if national else esc(L.country(cc))}</a></h3>
{f'<div class="chips" style="margin-top: 16px">{chips}</div>' if chips else ''}
{more}</article>""")
    others = [cc for cc in public_ccs if cc not in groups]
    public_chips = "".join(f'<a class="chip" href="{public_country_url(lang, cc)}">{esc(L.country(cc))}</a>'
                           for cc in sorted(others, key=L.country))
    faq = [(L.t("home_q_free"), L.t("home_a_free")), (L.t("home_q_update"), L.t("home_a_update")),
           (L.t("home_q_apps"), L.t("home_a_apps"))]
    faq_section, faq_ld = faq_html(L, faq)
    steps = "".join(f'<li><span class="step-n">{i}</span><span>{esc(L.t(k))}</span></li>'
                    for i, k in enumerate(("home_step1", "home_step2", "home_step3"), 1))
    submit = "/submit/?lang=de" if lang == "de" else "/submit/"
    body = f"""<section>
  <div class="wrap hero home-hero">
    <div>
      <p class="overline">{esc(L.t('home_overline'))}</p>
      <h1 class="display">{esc(L.t('home_h1'))}</h1>
      <p class="body-l">{esc(L.t('home_lead'))}</p>
      <form class="card" style="padding: 20px; max-width: 560px" action="/calendar/" method="get" role="search">
        <label class="h3" for="home-q" style="display: block; margin-bottom: 12px">{esc(L.t('home_search_label'))}</label>
        <div class="field">
          <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>
          <input class="input" id="home-q" name="q" type="search" placeholder="{esc(L.t('home_search_ph'))}" autocomplete="off">
        </div>
      </form>
      <!--langs-->
    </div>
    <div class="card card-lg home-how">
      <h2 class="h3" style="margin-bottom: 16px">{esc(L.t('home_how'))}</h2>
      <ol class="steps">{steps}</ol>
      <div class="row" style="display: flex; flex-wrap: wrap; gap: 8px; margin-top: 20px">
        <span class="pill pill-neutral">Apple Calendar</span><span class="pill pill-neutral">Google Calendar</span><span class="pill pill-neutral">Outlook</span>
      </div>
    </div>
  </div>
</section>
<section id="countries" style="padding-top: 0">
  <div class="wrap">
    <h2 class="h1" style="margin-bottom: 24px">{esc(L.t('home_countries'))}</h2>
    <div class="home-countries">{''.join(cards)}</div>
    <p class="body-s" style="margin-top: 16px"><a class="link-arrow" href="{submit}">{esc(L.t('home_submit'))}</a></p>
  </div>
</section>
{f'<section style="padding-top: 0"><div class="wrap"><h2 class="h2" style="margin-bottom: 16px">{esc(L.t("home_more_public"))}</h2><div class="chips">{public_chips}</div></div></section>' if public_chips else ''}
<section style="padding-top: 0"><div class="wrap gen">{faq_section}</div></section>
<section style="padding-top: 0">
  <div class="wrap">
    <div class="card">
      <h2 class="h3">{esc(L.t('home_dev'))}</h2>
      <p class="body-s muted" style="margin: 8px 0 16px">{esc(L.t('home_dev_text'))}</p>
      <a class="btn btn-secondary btn-sm" href="/docs/">{esc(L.t('home_dev_cta'))}</a>
    </div>
  </div>
</section>"""
    site_ld = {"@context": "https://schema.org", "@type": "WebSite", "name": "Holibase", "url": SITE + home_url(lang),
               "inLanguage": lang, "publisher": {"@id": f"{SITE}/#org"}}
    return page(lang, home_url(lang), L.t("home_title"), L.t("home_desc"), body, nav="home", ld=[site_ld, faq_ld],
                lastmod=today.isoformat(), group="home", meta_title=L.t("home_title"))


# ---------------------------------------------------------------- language links

def link_languages(pages: list[dict]) -> None:
    """Fill in hreflang alternates and the visible language switch for pages that exist in several languages."""
    groups = defaultdict(dict)
    for p in pages:
        if p.get("group"):
            groups[p["group"]][p["lang"]] = p["path"]
    for p in pages:
        alts = groups.get(p.get("group"), {})
        if len(alts) > 1:
            p["alternates"] = dict(alts)
            others = " · ".join(f'<a href="{alts[l]}" hreflang="{l}" lang="{l}">{LANG_NAMES[l]}</a>'
                                for l in LANGS if l in alts and l != p["lang"])
            switch = f'<p class="langs body-s">{esc(T[p["lang"]]["also_in"])}{Loc(p["lang"]).colon} {others}</p>'
        else:
            switch = ""
        p["body"] = p["body"].replace("<!--langs-->", switch)


# ---------------------------------------------------------------- entry point

def generate(snapshot: dict) -> tuple[list[dict], dict]:
    """Returns (pages, extras). extras: page map for the calendar app and lists for llms.txt."""
    today = d(snapshot["today"])
    scopes = [s for s in (Scope(r) for r in snapshot["scopes"]) if s.kept(today)]
    for s in scopes:  # a translation without dates for the current years is not worth a page
        s.langs = [l for l in s.langs if s.kept(today, l)]
    assign_slugs(scopes)
    by_cc = defaultdict(list)
    for s in scopes:
        by_cc[s.cc].append(s)
    public_langs = {c["cc"]: ["en"] + [l for l, hs in (c.get("l10n") or {}).items() if hs] for c in snapshot["public"]}

    pages = []
    school_urls = {}
    for lang in LANGS:
        if not any(lang in s.langs for s in scopes):
            continue
        pages.append(school_index(by_cc, today, lang))
        for cc, group in by_cc.items():
            g = [s for s in group if lang in s.langs]
            if not g:
                continue
            school_urls[(lang, cc)] = school_country_url(lang, cc)
            if len(group) == 1 and group[0].national:
                pages.append(scope_page(group[0], [], today, lang, public_langs))
                pages[-1]["group"] = f"school-country:{cc}"
            else:
                pages.append(country_school_page(cc, group, today, lang, public_langs))
                pages += [scope_page(s, group, today, lang, public_langs) for s in g]

    public_ccs = defaultdict(list)
    for lang in LANGS:
        for c in snapshot["public"]:
            if lang not in public_langs.get(c["cc"], ["en"]):
                continue
            p = public_country_page(c, school_urls, today, lang)
            if p:
                pages.append(p)
                public_ccs[lang].append(c["cc"])
        if public_ccs[lang]:
            pages.append(public_index(public_ccs[lang], today, lang))

    homes = {"en": "/"}
    for lang in LANGS[1:]:
        hp = home_page(lang, by_cc, public_ccs.get(lang, []), today)
        if hp:
            pages.append(hp)
            homes[lang] = hp["path"]

    link_languages(pages)
    for p in pages:  # the English home is a hand-written page: add it to the alternates and the language switch
        if p.get("group") == "home":
            p["alternates"] = dict(homes)
            others = " · ".join(f'<a href="{homes[l]}" hreflang="{l}" lang="{l}">{LANG_NAMES[l]}</a>'
                                for l in LANGS if l in homes and l != p["lang"])
            switch = f'<p class="langs body-s">{esc(T[p["lang"]]["also_in"])}{Loc(p["lang"]).colon} {others}</p>'
            p["body"] = re.sub(r'<p class="langs body-s">.*?</p>', lambda m: switch, p["body"], count=1, flags=re.S)
    page_map = {s.key: s.url("en") for s in scopes}
    page_map.update({f"public:{cc}": public_country_url("en", cc) for cc in public_ccs["en"]})
    extras = {"page_map": page_map, "school_ccs": sorted(by_cc), "public_ccs": public_ccs["en"],
              "scope_count": len(scopes), "coverage": snapshot.get("coverage"),
              "localized": {l: school_index_url(l) for l in LANGS if l != "en" and any(l in s.langs for s in scopes)},
              "homes": homes}
    return pages, extras


def coverage_rows(coverage: dict) -> str:
    """Server-rendered rows of the coverage table (coverage.js refreshes them live)."""
    L = Loc("en")
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
                   f'<td class="num">{esc(years)}</td><td>{esc(", ".join(dict.fromkeys(("OpenHolidays (ODbL)" if src == "openholidays" else "python-holidays" if src == "python-holidays" else None) or L.origin(o) for o, src in _origin_source_pairs(x))))}</td></tr>')
    return "".join(out)


def _origin_source_pairs(x: dict):
    """(origin, source) pairs for a coverage row; sources are listed separately by get_coverage()."""
    srcs = x.get("sources") or []
    for src in srcs:
        if src in ("openholidays", "python-holidays"):
            yield ("library", src)
    for o in x["origins"]:
        if o != "library" or not srcs:
            yield (o, None)


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
