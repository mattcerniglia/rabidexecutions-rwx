"""Offline: dialect inheritance + per-attribute test reach, from pristine source + coverage map."""
import ast, json, os, re, sys
m = json.load(open("map.json"))
SRC = "src"
# 1. dialect hierarchy: module X -> descendants (transitive)
parents = {}   # module -> set(parent modules)
D = os.path.join(SRC, "sqlglot", "dialects")
for fn in os.listdir(D):
    if not fn.endswith(".py") or fn.startswith("__"): continue
    mod = fn[:-3]
    tree = ast.parse(open(os.path.join(D, fn)).read())
    imported = {}  # name -> module
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module and n.module.startswith("sqlglot.dialects."):
            src_mod = n.module.split(".")[2]
            for a in n.names: imported[a.asname or a.name] = src_mod
    for n in tree.body:
        if isinstance(n, ast.ClassDef):
            for b in n.bases:
                if isinstance(b, ast.Name) and b.id in imported and imported[b.id] not in ("dialect", mod):
                    parents.setdefault(mod, set()).add(imported[b.id])
kids = {}
for c, ps in parents.items():
    for p in ps: kids.setdefault(p, set()).add(c)
def desc(x, seen=None):
    seen = seen or set()
    for k in kids.get(x, ()):
        if k not in seen: seen.add(k); desc(k, seen)
    return seen
children = {p: sorted(desc(p)) for p in kids}
# 2. attribute -> union of tests covering any line that references the name
lines_cache = {}
for f in m["lines"]:
    lines_cache[f] = open(os.path.join(SRC, f)).read().split("\n")
names = set()
for f, ls in lines_cache.items():
    if not re.match(r"sqlglot/(dialects|parsers|generators|typing)/", f): continue
    for l in ls:
        mm = re.match(r"^\s{4}([A-Z_][A-Z0-9_]*)\s*(?::[^=]+)?=\s", l)
        if mm: names.add(mm.group(1))
attrs = {}
importref = set()
sets = m["sets"]
for name in sorted(names):
    pat = re.compile(r"\b%s\b" % re.escape(name))
    ts = set()
    for f, ls in lines_cache.items():
        cov = m["lines"][f]
        for i, l in enumerate(ls, 1):
            if l.lstrip().startswith("#") or not pat.search(l): continue
            if i in set(m["import"].get(f, ())) and not re.match(r"^\s{4}%s\s*(?::[^=]+)?=\s" % re.escape(name), l):
                importref.add(name)
            s = cov.get(str(i))
            if s is not None: ts.update(sets[s])
    attrs[name] = sorted(ts)
json.dump({"children": children, "attrs": attrs, "importref": sorted(importref)}, open("attr_map.json", "w"), separators=(",", ":"))
print("children", {k: v for k, v in children.items()}, "attrs", len(attrs), "importref", len(importref), "bytes", os.path.getsize("attr_map.json"))
