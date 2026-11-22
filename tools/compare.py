import json, os, subprocess, sys
t = json.load(open("mut/tests.json"))["tests"]
num = {x["id"]: x["number"] for x in t}
sec = {x["number"]: round(x["seconds"] * 1000) for x in t}
meta = json.load(open("mut/meta.json"))
env = dict(os.environ, BR_DATA=os.path.abspath("mut"))
out = subprocess.run([sys.executable, "selector.py"], env=env, capture_output=True, text=True).stdout
sel = {}
for l in out.splitlines():
    d = json.loads(l); sel[d["commit"]] = d["workers"]
tot = 0; n = 0; miss = 0
for cid, m in meta.items():
    p = f"out/mutres/{cid}.json"
    if cid == "m000" or not os.path.exists(p): continue
    fails = {num[i] for i in json.load(open(p)) if i in num}
    w = sel[cid]; chosen = {x for ws in w for x in ws}
    cost = (max(sum(sec[x] for x in ws) for ws in w) + 2000 * len(w)) / 1000 if w else 0
    missing = fails - chosen
    n += 1; tot += cost; miss += bool(missing)
    flag = "MISS" if missing else "ok"
    print(cid, flag, f"fail={len(fails)} sel={len(chosen)} cost={cost:.1f}", m["file"], m["line"], m["new"].strip()[:60])
    for x in sorted(missing)[:3]: print("    missing:", t[x]["id"])
print(f"{n} mutants, {miss} with misses, mean cost {tot/max(n,1):.1f}s (+300 per miss)")
