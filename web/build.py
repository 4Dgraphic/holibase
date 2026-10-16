"""
Assemble the static site into web/public/.

    python web/build.py                 # hand-written pages; plus generated pages if web/.cache/snapshot.json exists
    DATABASE_URL=... python web/build.py --fetch   # refresh the snapshot from the database first

Hand-written pages live in web/src/pages/*.html and start with a front-matter block:
    <!--
    path: /coverage/
    title: Coverage
    description: ...
    theme: dark | light
    nav: coverage
    script: coverage.js
    -->
Generated pages (one per school calendar region and per country) come from generate.py.
"""
import datetime as dt
import json
import os
import pathlib
import re
import shutil
import sys

ROOT = pathlib.Path(__file__).parent
SRC, OUT = ROOT / "src", ROOT / "public"
SNAPSHOT = ROOT / ".cache" / "snapshot.json"
SITE = "https://holibase.org"
GENERATED_DIRS = ["school-holidays", "public-holidays"]

ORG = {"@type": "Organization", "@id": f"{SITE}/#org", "name": "Holibase", "url": SITE,
       "logo": f"{SITE}/assets/logo-512.png", "sameAs": ["https://github.com/4Dgraphic/holibase"]}


def partial(name: str) -> str:
    return (SRC / "partials" / f"{name}.html").read_text()


def home_ld(stats: dict) -> list:
    countries = stats.get("ph-countries", "247")
    return [
        {"@context": "https://schema.org", **ORG},
        {"@context": "https://schema.org", "@type": "WebSite", "@id": f"{SITE}/#site", "name": "Holibase", "url": SITE,
         "publisher": {"@id": f"{SITE}/#org"}, "inLanguage": "en"},
        {"@context": "https://schema.org", "@type": "Dataset", "name": "Holibase: public and school holidays worldwide",
         "description": f"Public holidays for {countries} countries and school holidays by region and US school district, "
                        "with sources, as open data, a free JSON API and iCalendar feeds.",
         "url": SITE, "sameAs": "https://github.com/4Dgraphic/holibase",
         "keywords": ["public holidays", "school holidays", "school calendar", "bank holidays", "school districts", "iCalendar"],
         "license": "https://creativecommons.org/licenses/by/4.0/", "isAccessibleForFree": True,
         "creator": {"@id": f"{SITE}/#org"}, "publisher": {"@id": f"{SITE}/#org"},
         "temporalCoverage": f"{stats.get('ph-first-year', '2020')}/{stats.get('ph-last-year', '2036')}",
         "spatialCoverage": {"@type": "Place", "name": "Worldwide"},
         "distribution": [
             {"@type": "DataDownload", "encodingFormat": "application/json", "contentUrl": "https://api.holibase.org/v1/public-holidays/US/2027"},
             {"@type": "DataDownload", "encodingFormat": "text/calendar", "contentUrl": "https://api.holibase.org/v1/public-holidays/US.ics"},
         ]},
    ]


def render(meta: dict, body: str, ld: list | None = None) -> str:
    logo = partial("logo").strip()
    path = meta["path"]
    title = meta["title"] if path == "/" else f"{meta['title']} · Holibase"
    header = partial("header").replace("{{logo}}", logo)
    for nav in ("calendar", "coverage", "docs", "licence"):
        header = header.replace("{{cur:%s}}" % nav, ' aria-current="page"' if meta.get("nav") == nav else "")
    scripts = '<script type="module" src="/assets/site.js"></script>'
    if meta.get("script"):
        scripts += f'\n<script type="module" src="/assets/{meta["script"]}"></script>'
    desc = meta["description"].replace('"', "&quot;")
    t = title.replace('"', "&quot;")
    canonical = SITE + ("/404" if path == "/404" else path)
    ld_html = "".join(f'<script type="application/ld+json">{json.dumps(x, ensure_ascii=False)}</script>\n' for x in (ld or []))
    robots = '<meta name="robots" content="noindex">\n' if meta.get("noindex") or path == "/404" else ""
    return f"""<!doctype html>
<html lang="en" data-theme="{meta.get('theme', 'dark')}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{t}</title>
<meta name="description" content="{desc}">
{robots}<link rel="canonical" href="{canonical}">
<meta property="og:site_name" content="Holibase">
<meta property="og:title" content="{t}">
<meta property="og:description" content="{desc}">
<meta property="og:url" content="{canonical}">
<meta property="og:type" content="website">
<meta property="og:image" content="{SITE}/assets/og.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta name="theme-color" content="{'#f6f8f9' if meta.get('theme') == 'light' else '#0a1c24'}">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/assets/logo-512.png">
<link rel="preload" href="/assets/fonts/outfit-latin-wght-normal.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="/assets/fonts/inter-latin-wght-normal.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="/assets/site.css">
{meta.get('head', '')}
{ld_html}</head>
<body>
{header}
<main id="main">
{body.replace('{{logo}}', logo)}
</main>
{partial('footer').replace('{{logo}}', logo)}
{scripts}
</body>
</html>
"""


def target_for(path: str) -> pathlib.Path:
    if path == "/404":
        return OUT / "404.html"
    return OUT / (path.strip("/") + "/index.html" if path != "/" else "index.html")


def bake_stats(body: str, stats: dict) -> str:
    """Put current figures into data-stat spans, so the HTML is right before any JavaScript runs."""
    for key, value in stats.items():
        body = re.sub(r'(data-stat="%s"[^>]*>)[^<]*(<)' % re.escape(key), lambda m: m.group(1) + value + m.group(2), body)
    return body


def llms_txt(stats: dict, extras: dict | None) -> str:
    lines = [
        "# Holibase",
        "",
        f"> Open data for public and school holidays worldwide: public holidays for {stats.get('ph-countries', '247')} countries "
        "and school holidays by region, zone and US school district, with sources. Free JSON API without key, iCalendar feeds, "
        "data under CC BY 4.0. Non-profit.",
        "",
        "Every date names its source. Official open data is used where a government publishes it (France, Netherlands), "
        "python-holidays for public holidays, and calendars researched from each authority's own documents elsewhere. "
        "When citing, credit: \"Public holidays © python-holidays contributors (MIT). School calendars © Holibase contributors (CC BY 4.0). https://holibase.org\".",
        "",
        "## API",
        "",
        "- [Getting started](https://holibase.org/docs/): endpoints, parameters, feeds, limits, licence",
        "- [OpenAPI 3.1 spec](https://api.holibase.org/openapi.json): machine-readable description of every endpoint and field",
        "- [Coverage](https://api.holibase.org/v1/coverage): live JSON of what is covered",
        "- Example: https://api.holibase.org/v1/public-holidays/DE/2027?subdivision=DE-BY",
        "- Example: https://api.holibase.org/v1/school-holidays/DE?subdivision=DE-NI",
        "- Example: https://api.holibase.org/v1/authorities?country=US&q=gwinnett",
        "",
        "## Pages",
        "",
        "- [School holidays by country](https://holibase.org/school-holidays/)",
        "- [Public holidays by country](https://holibase.org/public-holidays/)",
        "- [Coverage](https://holibase.org/coverage/)",
        "- [Sources and licences](https://holibase.org/licence/)",
    ]
    if extras:
        lines += ["", "## School holidays", ""]
        lines += [f"- [School holidays in {cc}](https://holibase.org/school-holidays/{cc.lower()}/)" for cc in extras["school_ccs"]]
    return "\n".join(lines) + "\n"


def build(fetch: bool = False) -> None:
    if fetch:
        import snapshot
        dsn = os.environ.get("DATABASE_URL")
        if not dsn:
            sys.exit("--fetch needs DATABASE_URL")
        data = snapshot.fetch(dsn)
        # Guard against a broken database read wiping hundreds of pages from the live site.
        if len(data["scopes"]) < 100 or len(data["public"]) < 200:
            sys.exit(f"snapshot looks incomplete ({len(data['scopes'])} school scopes, {len(data['public'])} countries); not building")
        SNAPSHOT.parent.mkdir(exist_ok=True)
        SNAPSHOT.write_text(json.dumps(data, default=str, ensure_ascii=False))
        print(f"snapshot: {len(data['scopes'])} school scopes, {len(data['public'])} countries")

    snap = json.loads(SNAPSHOT.read_text()) if SNAPSHOT.exists() else None
    stats, extras, generated = {}, None, []
    if snap:
        import generate
        generated, extras = generate.generate(snap)
        if snap.get("coverage"):
            stats = generate.stats(snap["coverage"])
    else:
        print("no snapshot: building hand-written pages only (run with --fetch to add the generated pages)")

    for d in GENERATED_DIRS:
        shutil.rmtree(OUT / d, ignore_errors=True)

    today = dt.date.today().isoformat()
    urls = []
    for page in sorted((SRC / "pages").glob("*.html")):
        text = page.read_text()
        m = re.match(r"<!--(.*?)-->\s*", text, re.S)
        meta = {k.strip(): v.strip() for k, v in (line.split(":", 1) for line in m.group(1).strip().splitlines())}
        body = bake_stats(text[m.end():], stats)
        if snap and "<!--coverage-rows-->" in body:
            import generate
            body = body.replace('<tr><td colspan="6" class="muted">Loading…</td></tr>', "").replace("<!--coverage-rows-->", generate.coverage_rows(snap["coverage"]))
        if extras and "<!--country-chips-->" in body:
            import generate
            chips = "".join(f'<a class="chip" href="/public-holidays/{cc.lower()}/">{generate.esc(generate.country_name(cc))}</a>'
                            for cc in sorted(extras["public_ccs"], key=generate.country_name))
            body = body.replace("<!--country-chips-->", chips)
        ld = home_ld(stats) if meta["path"] == "/" else None
        target = target_for(meta["path"])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render(meta, body, ld))
        if meta["path"] != "/404":
            urls.append((SITE + meta["path"], today))

    for p in generated:
        target = target_for(p["path"])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render(p, p["body"], p["ld"]))
        urls.append((SITE + p["path"], p.get("lastmod") or today))
    print(f"wrote {len(urls)} pages ({len(generated)} generated)")

    (OUT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"  <url><loc>{u}</loc><lastmod>{lm}</lastmod></url>\n" for u, lm in urls) + "</urlset>\n")
    (OUT / "llms.txt").write_text(llms_txt(stats, extras))
    (OUT / "assets" / "pages.json").write_text(json.dumps(extras["page_map"] if extras else {}, separators=(",", ":")))


if __name__ == "__main__":
    build(fetch="--fetch" in sys.argv)
