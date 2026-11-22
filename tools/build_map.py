"""cov.dat + opens.json + tests.json -> map.json (plain file committed to repo)."""
import json, sys, os
import coverage
cov_path, opens_path, tests_path, out_path = sys.argv[1:5]
tests = json.load(open(tests_path))["tests"]
num = {t["id"]: t["number"] for t in tests}
d = coverage.CoverageData(cov_path); d.read()
lines = {}   # file -> {line: sorted test nums}
imp = {}     # file -> [lines executed at import / outside any test]
unknown = set()
for f in d.measured_files():
    rel = os.path.relpath(f, "/work")
    per = {}
    for ln, ctxs in d.contexts_by_lineno(f).items():
        ts = set()
        for c in ctxs:
            if c == "":
                imp.setdefault(rel, []).append(ln)
            elif c.startswith("SCOPE::"):
                pre = c[7:]
                for tid, tn in num.items():
                    if pre == "" or tid.startswith(pre + "::") or tid == pre:
                        ts.add(tn)
            elif c in num:
                ts.add(num[c])
            else:
                unknown.add(c)
        if ts:
            per[ln] = sorted(ts)
    lines[rel] = per
opens = json.load(open(opens_path))
fix = {}
for ctx, files in opens.items():
    if ctx in num:
        for p in files:
            r = os.path.relpath(p, "/work")
            fix.setdefault(r, set()).add(num[ctx])
    else:
        for p in files:
            fix.setdefault(os.path.relpath(p, "/work"), set())  # opened outside a test
fix = {k: sorted(v) for k, v in fix.items()}
# dedupe test-lists: table of unique sets
uniq, idx = [], {}
comp = {}
for f, per in lines.items():
    comp[f] = {}
    for ln, ts in per.items():
        k = tuple(ts)
        if k not in idx:
            idx[k] = len(uniq); uniq.append(ts)
        comp[f][ln] = idx[k]
import ast
spans, stmts = {}, {}
for f in comp:
    try:
        src = open(os.path.join("/work", f)).read()
        tree = ast.parse(src)
    except Exception:
        continue
    sp, st = [], []
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            start = min([n.lineno] + [x.lineno for x in n.decorator_list])
            sp.append([start, n.end_lineno, 1 if isinstance(n, ast.ClassDef) else 0, n.body[0].lineno])
        if isinstance(n, ast.stmt):
            body = getattr(n, "body", None)
            if isinstance(body, list) and body:
                hs, he = n.lineno, body[0].lineno - 1
            else:
                hs, he = n.lineno, n.end_lineno
            if he > hs:
                st.append([hs, he])
    spans[f] = sp; stmts[f] = st
ids = [t["id"] for t in tests]
json.dump({"ids": ids, "spans": spans, "stmts": stmts, "sets": uniq, "lines": comp, "import": imp, "fixtures": fix}, open(out_path, "w"), separators=(",", ":"))
print("files", len(comp), "uniqsets", len(uniq), "unknown ctx", list(unknown)[:5], "fixtures", len(fix), file=sys.stderr)
