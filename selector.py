"""Blast Radius selector: per-test line-coverage map (built from the pinned sqlglot
commit) + patch hunks -> the tests that execute the changed code."""

import json
import os
import re
import sys
from pathlib import Path

DATA = Path(os.environ.get("BR_DATA", "/data"))
MAP = Path(__file__).with_name("map.json")
WORKER_COST = 2000
HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def parse_patch(text):
    """-> {path: (removed_old_lines, inserted_before_old_lines)}"""
    files = {}
    cur = None
    old = 0
    for line in text.split("\n"):
        if line.startswith("diff --git"):
            m = re.match(r"diff --git a/(.*) b/(.*)$", line)
            cur = m.group(2) if m else None
            if cur:
                files.setdefault(cur, ([], []))
            continue
        if line.startswith("--- ") or line.startswith("+++ "):
            continue
        m = HUNK.match(line)
        if m:
            old = int(m.group(1))
            continue
        if cur is None:
            continue
        removed, added = files[cur]
        if line.startswith("-"):
            removed.append(old)
            old += 1
        elif line.startswith("+"):
            added.append(old)
        elif line.startswith(" "):
            old += 1
    return files


class Mapper:
    def __init__(self, tests):
        m = json.loads(MAP.read_text())
        self.m = m
        by_id = {t["id"]: t["number"] for t in tests}
        num = [by_id.get(i) for i in m["ids"]]
        self.sets = [[num[i] for i in s if num[i] is not None] for s in m["sets"]]
        self.fixtures = {
            k: [num[i] for i in v if num[i] is not None] for k, v in m["fixtures"].items()
        }
        self.by_file = {}
        for t in tests:
            self.by_file.setdefault(t["file"], []).append(t["number"])
        self.all = [t["number"] for t in tests]
        self.cache = {}

    def tests_at(self, f, line):
        i = self.m["lines"][f].get(str(line))
        return self.sets[i] if i is not None else ()

    def norm(self, f, line):
        """Move a line inside a multi-line statement (header) to its first line."""
        best = None
        for a, b in self.m["stmts"].get(f, ()):
            if a <= line <= b and (best is None or b - a < best[1] - best[0]):
                best = (a, b)
        return best[0] if best else line

    def func_union(self, f, line):
        """Union of tests covering any line of the innermost def/class around `line`."""
        best = None
        for a, b, _cls, _fb in self.m["spans"].get(f, ()):
            if a <= line <= b and (best is None or b - a < best[1] - best[0]):
                best = (a, b)
        lo, hi = best if best else (1, 10**9)
        key = (f, lo, hi)
        if key not in self.cache:
            out = set()
            for ln, i in self.m["lines"][f].items():
                if lo <= int(ln) <= hi:
                    out.update(self.sets[i])
            self.cache[key] = out
        return self.cache[key]

    def select_py(self, f, removed, added):
        out = set()
        imp = set(self.m["import"].get(f, ()))
        for L in removed:
            n = self.norm(f, L)
            ts = self.tests_at(f, n)
            if ts:
                out.update(ts)
            elif n in imp or L in imp:
                out.update(self.func_union(f, n))  # import-only line: widen
        for L in added:
            for k in (L - 1, L):
                out.update(self.tests_at(f, self.norm(f, k)))
            out.update(self.func_union(f, max(L - 1, 1)))
        return out

    def select(self, files):
        """-> set of test numbers, or None meaning 'run everything'."""
        out = set()
        for path, (removed, added) in files.items():
            if path in self.m["lines"]:
                out.update(self.select_py(path, removed, added))
            elif path.startswith("tests/fixtures/"):
                out.update(self.fixtures.get(path, ()))
            elif path.startswith("tests/") and path.endswith(".py"):
                out.update(self.by_file.get(path, ()))
                if path.endswith(("helpers.py", "conftest.py", "__init__.py")):
                    return None
            elif path in ("pyproject.toml", "setup.py", "setup.cfg"):
                return None
        return out


def split(chosen, secs):
    """Pick the worker count in 1..8 minimizing max-load + 2s per worker."""
    if not chosen:
        return []
    order = sorted(chosen, key=lambda t: -secs[t])
    best = None
    for w in range(1, min(8, len(order)) + 1):
        loads = [0] * w
        groups = [[] for _ in range(w)]
        for t in order:
            j = loads.index(min(loads))
            groups[j].append(t)
            loads[j] += secs[t]
        cost = max(loads) + WORKER_COST * w
        if best is None or cost < best[0]:
            best = (cost, groups)
    return best[1]


def main():
    tests = json.loads((DATA / "tests.json").read_text())["tests"]
    secs = {t["number"]: round(t["seconds"] * 1000) for t in tests}
    mp = Mapper(tests)
    for patch in sorted((DATA / "commits").glob("*.patch")):
        try:
            sel = mp.select(parse_patch(patch.read_text(errors="replace")))
            chosen = mp.all if sel is None else sorted(sel)
        except Exception as e:  # never crash: fall back to everything
            print(f"{patch.stem}: {e!r}", file=sys.stderr)
            chosen = mp.all
        print(json.dumps({"commit": patch.stem, "workers": split(chosen, secs)}))


if __name__ == "__main__":
    main()
