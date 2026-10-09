"""Per-country fingerprints of library data, to compare a fresh build with the database."""
import hashlib, json, sys, time
sys.path.insert(0, "scripts")
import build

def ph_line(r):
    names = ",".join(f"{k}={v}" for k, v in sorted(r["names"].items()))
    return "|".join([r["country_code"], r["subdivision_code"] or "", r["date"], r["category"], r["scope"],
                     r["local_name"], "t" if r["is_observed"] else "f", "t" if r["is_estimated"] else "f", names])

def sc_line(cc, cal, p):
    names = ",".join(f"{k}={v}" for k, v in sorted(p["names"].items()))
    return "|".join([cc, cal["subdivision_code"] or "", cal["school_year"], p["start_date"], p["end_date"], p["kind"], p["label"], names])

def fp(lines):
    hs = sorted(hashlib.md5(l.encode()).hexdigest() for l in lines)
    return len(hs), hashlib.md5("".join(hs).encode()).hexdigest()

years = list(range(2020, 2031))
out = {}
t = time.time()
for info, ph, sc in build.build(build.supported_countries(), years):
    cc = info["code"]
    out[cc] = {"ph": fp(ph_line(r) for r in ph),
               "sc": fp(sc_line(cc, c, p) for c in sc for p in c["periods"]) if sc else (0, None)}
json.dump(out, open(sys.argv[1] if len(sys.argv) > 1 else "fingerprints.json", "w"))
print(len(out), "countries", round(time.time() - t, 1), "s")
