"""Second mutant set: class/module-level constants and def-header defaults in lazily imported modules."""
import ast, difflib, json, os, random, re, sys
SRC, N, OUT, seed = sys.argv[1], int(sys.argv[2]), sys.argv[3], int(sys.argv[4])
random.seed(seed)
m = json.load(open("map.json"))
files = [f for f in m["lines"] if re.match(r"sqlglot/(optimizer|executor|dialects|parsers|generators|typing|planner)/", f)]
random.shuffle(files)
os.makedirs(OUT + "/commits", exist_ok=True)
meta, tries = {}, 0
def mutate(line):
    masked = re.sub(r'(\"[^\"]*\"|\'[^\']*\')', lambda x: "_" * len(x.group()), line)
    opts = []
    for a, b in (("True", "False"), ("False", "True"), ("= 0", "= 1"), ("= 1", "= 2"), ("= -1", "= -2"), (" None", " 0")):
        if a in masked: opts.append((masked.index(a), a, b))
    for mm in re.finditer(r"(?<![\w.])(\d+)(?![\w.])", masked):
        opts.append((mm.start(1), mm.group(1), str(int(mm.group(1)) + 1)))
    if not opts: return None
    i, a, b = random.choice(opts)
    return line[:i] + b + line[i + len(a):]
for f in files:
    if len(meta) >= N: break
    src = open(os.path.join(SRC, f)).read().split("\n")
    tree = ast.parse("\n".join(src))
    cand = []
    for n in ast.walk(tree):
        if isinstance(n, ast.ClassDef):
            cand += [s.lineno for s in n.body if isinstance(s, (ast.Assign, ast.AnnAssign)) and s.lineno == s.end_lineno]
        if isinstance(n, (ast.FunctionDef,)):
            cand += [a.lineno for a in n.args.defaults if isinstance(a, ast.Constant)]
    cand += [s.lineno for s in tree.body if isinstance(s, (ast.Assign, ast.AnnAssign)) and s.lineno == s.end_lineno]
    random.shuffle(cand)
    for l in cand[:3]:
        new = mutate(src[l - 1])
        if not new or new == src[l - 1]: continue
        mod = src[:l - 1] + [new] + src[l:]
        try: ast.parse("\n".join(mod))
        except Exception: continue
        cid = "n%03d" % len(meta)
        d = list(difflib.unified_diff(src, mod, "a/" + f, "b/" + f, lineterm="", n=3))
        open(f"{OUT}/commits/{cid}.patch", "w").write(f"diff --git a/{f} b/{f}\n" + "\n".join(d) + "\n")
        meta[cid] = {"file": f, "line": l, "old": src[l - 1], "new": new}
        break
json.dump(meta, open(OUT + "/meta.json", "w"), indent=1)
print(len(meta), "mutants")
