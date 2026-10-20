"""
Read everything the generated pages need from the database into one JSON file.

    DATABASE_URL=postgresql://... python web/snapshot.py      # writes web/.cache/snapshot.json

Read-only: the connection runs in a read-only transaction. Three queries, a few seconds.
The pages are built from this file by web/build.py, so the site stays fully static.
"""
import datetime as dt
import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).parent

# Languages the generated pages are translated into, per country (see generate.py).
SCHOOL_LANGS = {"DE": ["de"], "AT": ["de"], "CH": ["de", "fr", "it"], "FR": ["fr"], "BE": ["fr", "nl"], "NL": ["nl"],
                "LU": ["fr", "de"], "LI": ["de"], "ES": ["es"], "IT": ["it"], "SM": ["it"], "PL": ["pl"], "PT": ["pt"],
                "CZ": ["cs"], "SK": ["sk"], "RO": ["ro"], "MD": ["ro"], "MX": ["es"]}
_ES = ["ES", "MX", "AR", "CL", "CO", "PE", "VE", "EC", "GT", "CU", "BO", "DO", "HN", "PY", "SV", "NI", "CR", "PA", "UY"]
PUBLIC_LANGS = {"DE": ["de"], "AT": ["de"], "CH": ["de", "fr", "it"], "LI": ["de"], "LU": ["de", "fr"],
                "FR": ["fr"], "BE": ["fr", "nl"], "MC": ["fr"], "NL": ["nl"],
                **{cc: ["es"] for cc in _ES}, "IT": ["it"], "SM": ["it"], "VA": ["it"], "PL": ["pl"],
                "PT": ["pt"], "BR": ["pt"], "AO": ["pt"], "MZ": ["pt"], "CZ": ["cs"], "SK": ["sk"], "RO": ["ro"], "MD": ["ro"]}


def lang_case(column: str, mapping: dict) -> str:
    """SQL expression: the languages of a country code as a text[]."""
    whens = " ".join(f"when '{cc}' then array[{', '.join(repr(l) for l in ls)}]" for cc, ls in mapping.items())
    return f"(case {column} {whens} else array[]::text[] end)"

OUT = ROOT / ".cache" / "snapshot.json"

# One row per school calendar scope (region, zone, district) with its periods, calendars and
# the public holidays of the same region. Window: the current and next school years.
SCOPES_SQL = """
with scopes as (
  select distinct c.country_code::text as cc, c.subdivision_code as sub, c.authority_id as auth
    from public.school_calendars c
   where c.status = 'confirmed' {filter}
)
select coalesce(json_agg(x order by x->>'cc', x->>'sub', x->>'auth_name'), '[]'::json) from (
  select json_build_object(
    'cc', s.cc,
    'sub', s.sub,
    'auth', s.auth,
    'auth_name', a.name, 'auth_city', a.city, 'auth_kind', a.kind, 'auth_sub', a.subdivision_code,
    'auth_students', a.student_count, 'auth_ids', a.external_ids,
    'sub_name', sd.name,
    'periods', (select coalesce(json_agg(h order by h.start_date), '[]'::json)
                  from public.get_school_holidays(s.cc, %(from)s, %(to)s, s.sub, s.auth, 'en') h),
    'calendars', (select coalesce(json_agg(k order by k.school_year), '[]'::json)
                    from public.get_school_calendars(s.cc, %(from)s, %(to)s, s.sub, s.auth) k),
    'public', (select coalesce(json_agg(p order by p.date), '[]'::json)
                 from public.get_public_holidays(s.cc, %(today)s, %(year_ahead)s, coalesce(s.sub, a.subdivision_code), 'en') p),
    'l10n', (select coalesce(json_object_agg(l, json_build_object(
                'periods', (select coalesce(json_agg(h order by h.start_date), '[]'::json)
                              from public.get_school_holidays(s.cc, %(from)s, %(to)s, s.sub, s.auth, l) h),
                'public', (select coalesce(json_agg(p order by p.date), '[]'::json)
                             from public.get_public_holidays(s.cc, %(today)s, %(year_ahead)s, coalesce(s.sub, a.subdivision_code), l) p))), '{{}}'::json)
               from unnest({school_langs}) l)
  ) as x
    from scopes s
    left join public.education_authorities a on a.id = s.auth
    left join public.subdivisions sd on sd.code = coalesce(s.sub, a.subdivision_code)
) q
"""

# Nationwide public holidays per country, this year and next.
PUBLIC_SQL = """
select coalesce(json_agg(x order by x->>'cc'), '[]'::json) from (
  select json_build_object(
    'cc', c.code::text,
    'default_language', c.default_language,
    'subdivisions', (select count(*) from public.subdivisions s where s.country_code = c.code),
    'holidays', (select coalesce(json_agg(p order by p.date), '[]'::json)
                   from public.get_public_holidays(c.code::text, %(y0)s, %(y1)s, null, 'en') p),
    'l10n', (select coalesce(json_object_agg(l, (select coalesce(json_agg(p order by p.date), '[]'::json)
                from public.get_public_holidays(c.code::text, %(y0)s, %(y1)s, null, l) p)), '{{}}'::json)
               from unnest({public_langs}) l)
  ) as x
  from public.countries c {filter}
) q
"""


def fetch(dsn: str, countries: list[str] | None = None) -> dict:
    import psycopg

    today = dt.date.today()
    params = {
        "today": today,
        "from": today - dt.timedelta(days=200),
        "to": today + dt.timedelta(days=760),
        "year_ahead": today + dt.timedelta(days=365),
        "y0": dt.date(today.year, 1, 1),
        "y1": dt.date(today.year + 1, 12, 31),
    }
    f_scopes = "and c.country_code = any(%(cc)s)" if countries else ""
    f_public = "where c.code = any(%(cc)s)" if countries else ""
    if countries:
        params["cc"] = countries
    with psycopg.connect(dsn) as conn:
        conn.read_only = True
        with conn.cursor() as cur:
            cur.execute(SCOPES_SQL.format(filter=f_scopes, school_langs=lang_case('s.cc', SCHOOL_LANGS)), params)
            scopes = cur.fetchone()[0]
            cur.execute(PUBLIC_SQL.format(filter=f_public, public_langs=lang_case('c.code::text', PUBLIC_LANGS)), params)
            public = cur.fetchone()[0]
            cur.execute("select public.get_coverage()")
            coverage = cur.fetchone()[0]
    return {"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "today": today.isoformat(), "scopes": scopes, "public": public, "coverage": coverage}


def main() -> None:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        sys.exit("DATABASE_URL is not set")
    countries = [c.strip().upper() for c in sys.argv[1:]] or None
    data = fetch(dsn, countries)
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(data, default=str, ensure_ascii=False))
    print(f"wrote {OUT.relative_to(ROOT.parent)}: {len(data['scopes'])} school scopes, {len(data['public'])} countries")


if __name__ == "__main__":
    main()
