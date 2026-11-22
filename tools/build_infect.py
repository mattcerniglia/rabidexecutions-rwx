"""infect.json (+ map.json ids) -> infect_map.json: per (file, line, col) site and alternative
operator, the tests where that alternative would have produced a different value."""
import json, sys
inf = json.load(open(sys.argv[1]))
m = json.load(open(sys.argv[2]))
out = sys.argv[3]
idx = {t: i for i, t in enumerate(m["ids"])}
sets, sidx = [], {}
def sid(ts):
    k = tuple(sorted(ts))
    if k not in sidx:
        sidx[k] = len(sets); sets.append(list(k))
    return sidx[k]
site = {}   # site id -> {alt: set of test idx}
def expand(t):
    if t in idx: return [idx[t]]
    if t.startswith("SCOPE::"):
        pre = t[7:]
        return [i for tid, i in idx.items() if pre == "" or tid.startswith(pre + "::") or tid == pre]
    return []
for t, per in inf["tests"].items():
    members = expand(t)
    for s, alts in per.items():
        d = site.setdefault(int(s), {})
        for a in alts:
            d.setdefault(a, set()).update(members)
sites = {}
for s, d in site.items():
    f, line, col, op = inf["sites"][s]
    sites.setdefault(f, {})[f"{line}:{col}"] = {"op": op, "alts": {a: sid(ts) for a, ts in d.items()}}
# every instrumented site, including those no test ever infected
known = {}
for s, (f, line, col, op) in enumerate(inf["sites"]):
    known.setdefault(f, {})[f"{line}:{col}"] = op
unprof = [idx[l.strip()] for l in open(sys.argv[4]) if l.strip() in idx] if len(sys.argv) > 4 else []
imp = sorted({f"{inf['sites'][s][0]}:{inf['sites'][s][1]}:{inf['sites'][s][2]}" for s in inf["import"]})
json.dump({"sets": sets, "sites": sites, "known": known, "import": imp, "unprofiled": sorted(set(unprof))}, open(out, "w"), separators=(",", ":"))
print("sites", sum(len(v) for v in sites.values()), "known", sum(len(v) for v in known.values()), "sets", len(sets), "import", len(imp))
