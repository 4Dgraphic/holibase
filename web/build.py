"""
Assemble the static site: web/src/pages/*.html + partials -> web/public/.

    python web/build.py

Each page starts with a front-matter block:
    <!--
    path: /coverage/
    title: Coverage
    description: ...
    theme: dark | light
    nav: coverage
    script: coverage.js
    -->
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).parent
SRC, OUT = ROOT / "src", ROOT / "public"
SITE = "https://holibase.org"


def partial(name: str) -> str:
    return (SRC / "partials" / f"{name}.html").read_text()


def build() -> None:
    logo = partial("logo").strip()
    urls = []
    for page in sorted((SRC / "pages").glob("*.html")):
        text = page.read_text()
        m = re.match(r"<!--(.*?)-->\s*", text, re.S)
        meta = dict(line.split(":", 1) for line in m.group(1).strip().splitlines())
        meta = {k.strip(): v.strip() for k, v in meta.items()}
        body = text[m.end():]
        path = meta["path"]
        title = meta["title"] if path == "/" else f"{meta['title']} · Holibase"
        header = partial("header").replace("{{logo}}", logo)
        for nav in ("calendar", "coverage", "docs", "licence"):
            header = header.replace("{{cur:%s}}" % nav, ' aria-current="page"' if meta.get("nav") == nav else "")
        scripts = '<script type="module" src="/assets/site.js"></script>'
        if meta.get("script"):
            scripts += f'\n<script type="module" src="/assets/{meta["script"]}"></script>'
        html = f"""<!doctype html>
<html lang="en" data-theme="{meta.get('theme', 'dark')}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{meta['description']}">
<link rel="canonical" href="{SITE}{path}">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{meta['description']}">
<meta property="og:url" content="{SITE}{path}">
<meta property="og:type" content="website">
<meta name="theme-color" content="{'#f6f8f9' if meta.get('theme') == 'light' else '#0a1c24'}">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="preload" href="/assets/fonts/outfit-latin-wght-normal.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="/assets/fonts/inter-latin-wght-normal.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="/assets/site.css">
{meta.get('head', '')}
</head>
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
        target = OUT / (path.strip("/") + "/index.html" if path != "/" else "index.html") if path != "/404" else OUT / "404.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(html)
        print("wrote", target.relative_to(ROOT))
        if path != "/404":
            urls.append(SITE + path)
    sitemap = "".join(f"  <url><loc>{u}</loc></url>\n" for u in urls)
    (OUT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + sitemap + "</urlset>\n")
    print("wrote public/sitemap.xml")


if __name__ == "__main__":
    build()
