"""
Contract test: call the live API and validate every response against its own OpenAPI description.

    python scripts/check_openapi.py [https://api.holibase.org]

Runs after every deploy (deploy-api workflow). A field that changes in the code without changing in
api/src/openapi.ts fails here, so the published docs cannot drift away from the API.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request

from jsonschema import Draft202012Validator

BASE = (sys.argv[1] if len(sys.argv) > 1 else "https://api.holibase.org").rstrip("/")
failures: list[str] = []


def get(path: str) -> tuple[int, dict[str, str], bytes]:
    req = urllib.request.Request(BASE + path, headers={"User-Agent": "holibase-contract-test/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, {k.lower(): v for k, v in r.headers.items()}, r.read()
    except urllib.error.HTTPError as e:
        return e.code, {k.lower(): v for k, v in e.headers.items()}, e.read()


spec = json.loads(get("/openapi.json")[2])


def validator(name: str) -> Draft202012Validator:
    return Draft202012Validator({"$ref": f"#/components/schemas/{name}", "components": spec["components"]})


def check(path: str, schema: str, status: int = 200) -> dict:
    code, headers, body = get(path)
    label = f"{path} -> {code}"
    if code != status:
        failures.append(f"{label}: expected HTTP {status}")
        return {}
    if "application/json" not in headers.get("content-type", ""):
        failures.append(f"{label}: content-type {headers.get('content-type')}")
        return {}
    data = json.loads(body)
    errors = sorted(validator(schema).iter_errors(data), key=lambda e: list(e.absolute_path))
    for e in errors[:5]:
        failures.append(f"{label}: {schema} at /{'/'.join(map(str, e.absolute_path))}: {e.message[:200]}")
    print(f"{'ok ' if not errors else 'BAD'} {label} ({schema})")
    return data


def check_ics(path: str) -> None:
    code, headers, body = get(path)
    ok = code == 200 and headers.get("content-type", "").startswith("text/calendar") and body.startswith(b"BEGIN:VCALENDAR")
    print(f"{'ok ' if ok else 'BAD'} {path} -> {code} (iCalendar)")
    if not ok:
        failures.append(f"{path}: expected an iCalendar feed, got {code} {headers.get('content-type')}")


# every operation in the spec must be exercised below
check("/v1/countries", "CountriesResponse")
check("/v1/public-holidays/DE/2026?subdivision=DE-BY&lang=de", "PublicHolidaysResponse")
check("/v1/public-holidays/US?from=2026-01-01&to=2026-12-31&subdivision=US-CA", "PublicHolidaysResponse")
check("/v1/school-holidays/DE?subdivision=DE-NI&from=2026-08-01&to=2027-07-31&lang=de", "SchoolHolidaysResponse")

found = check("/v1/authorities?country=US&q=gwinnett", "AuthoritySearchResponse")
if found.get("authorities"):
    aid = found["authorities"][0]["id"]
    check(f"/v1/authorities/{aid}", "AuthorityResponse")
    data = check(f"/v1/school-holidays/US?authority={aid}&from=2026-08-01&to=2027-07-31", "SchoolHolidaysResponse")
    if data and data.get("coverage", {}).get("status") != "available":
        failures.append("Gwinnett: expected coverage available")
else:
    failures.append("authority search for gwinnett returned nothing")

zone = check("/v1/authorities?country=FR&q=" + urllib.parse.quote("Zone A"), "AuthoritySearchResponse")
if zone.get("authorities"):
    check(f"/v1/school-holidays/FR?authority={zone['authorities'][0]['id']}&from=2026-09-01&to=2027-08-31&lang=fr", "SchoolHolidaysResponse")

none = check("/v1/authorities?country=US&q=" + urllib.parse.quote("Aransas Pass"), "AuthoritySearchResponse")
if none.get("authorities"):
    data = check(f"/v1/school-holidays/US?authority={none['authorities'][0]['id']}&from=2030-08-01&to=2031-07-31", "SchoolHolidaysResponse")
    if data and data.get("coverage", {}).get("status") != "none":
        failures.append("Aransas Pass 2030-31: expected coverage none")

check_ics("/v1/public-holidays/DE.ics?subdivision=DE-BY&lang=de")
check_ics("/v1/school-holidays/NL.ics?authority=" + (check("/v1/authorities?country=NL&q=Noord", "AuthoritySearchResponse").get("authorities") or [{"id": ""}])[0]["id"])
check("/v1/public-holidays/XX1", "Error", 400)
check("/v1/public-holidays/DE?from=2026-01-01&to=2031-01-01", "Error", 400)
check("/v1/authorities/00000000-0000-0000-0000-000000000000", "Error", 404)

code, _, body = get("/v1/health")
print(f"{'ok ' if code == 200 else 'BAD'} /v1/health -> {code}")
if code != 200:
    failures.append("/v1/health not 200")

if failures:
    print("\nContract test failed:")
    print("\n".join(f"- {f}" for f in failures))
    sys.exit(1)
print("\nAll responses match the OpenAPI description.")
