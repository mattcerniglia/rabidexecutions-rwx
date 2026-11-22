"""Generate single-line operator mutants of sqlglot as patches + meta."""
import ast, difflib, json, random, re, sys, os
SRC = sys.argv[1]; N = int(sys.argv[2]); OUT = sys.argv[3]; seed = int(sys.argv[4]) if len(sys.argv) > 4 else 7
random.seed(seed)
m = json.load(open("map.json"))
MUT = [(" and ", " or "), (" or ", " and "), (" == ", " != "), (" != ", " == "), (" is not ", " is "),
       (" is ", " is not "), (" > ", " < "), (" < ", " > "), (" >= ", " > "), (" <= ", " < "),
       ("not ", ""), ("True", "False"), ("False", "True"), (" + ", " - "), (" - ", " + "),
       ("= 0", "= 1"), ("= 1", "= 2"), ("-1", "-2"), (" in ", " not in "), (" if ", " if not ")]
cands = []
for f, lines in m["lines"].items():
    ls = set(int(x) for x in lines) | set(m["import"].get(f, []))
    cands += [(f, l) for l in ls]
random.shuffle(cands)
os.makedirs(OUT + "/commits", exist_ok=True)
meta = {}
cache = {}
for f, l in cands:
    if len(meta) >= N: break
    if f not in cache:
        cache[f] = open(os.path.join(SRC, f)).read().split("\n")
    src = cache[f]
    if l > len(src): continue
    line = src[l - 1]
    s = line.strip()
    if not s or s.startswith(("#", '"', "'", "def ", "class ", "import ", "from ", "@")): continue
    masked = re.sub(r'(\"[^\"]*\"|\'[^\']*\')', lambda x: "_" * len(x.group()), line)
    opts = [(a, b) for a, b in MUT if a in masked]
    if not opts: continue
    a, b = random.choice(opts)
    i = masked.index(a)
    new = line[:i] + b + line[i + len(a):]
    mod = src[:l - 1] + [new] + src[l:]
    try: ast.parse("\n".join(mod))
    except Exception: continue
    cid = "m%03d" % len(meta)
    diff = list(difflib.unified_diff(src, mod, "a/" + f, "b/" + f, lineterm="", n=3))
    open(f"{OUT}/commits/{cid}.patch", "w").write(f"diff --git a/{f} b/{f}\n" + "\n".join(diff) + "\n")
    meta[cid] = {"file": f, "line": l, "old": line, "new": new}
json.dump(meta, open(OUT + "/meta.json", "w"), indent=1)
print(len(meta), "mutants")
