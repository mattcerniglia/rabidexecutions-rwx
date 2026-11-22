"""Blast Radius selector: per-test line-coverage map (built from the pinned sqlglot
commit) + patch hunks -> the tests that execute the changed code."""

import json
import os
import re
import sys
from pathlib import Path

DATA = Path(os.environ.get("BR_DATA", "/data"))
MAP = Path(__file__).with_name("map.json")
SRC = Path(__file__).with_name("src")
INF = Path(__file__).with_name("infect_map.json")
ATTR = Path(__file__).with_name("attr_map.json")
ALTS = {
    "==": ["!=", "is"], "!=": ["==", "is not"], "<": ["<=", ">", ">="], "<=": ["<", ">", ">="],
    ">": [">=", "<", "<="], ">=": [">", "<", "<="], "is": ["is not", "=="], "is not": ["is", "!="],
    "in": ["not in"], "not in": ["in"],
}
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


class _LazySets:
    """Decode map test-index lists into runtime test numbers on first use."""

    def __init__(self, raw, num):
        self.raw, self.num, self.done = raw, num, {}

    def __getitem__(self, i):
        got = self.done.get(i)
        if got is None:
            got = self.done[i] = [self.num[j] for j in self.raw[i] if self.num[j] is not None]
        return got


STRUCTURAL = re.compile(
    r"^(deleted file mode|rename from|rename to|copy from|copy to|old mode|new mode|Binary files|GIT binary patch)",
    re.M,
)


def split_hunks(text):
    """-> {path: [(old_start, [hunk lines with their +/-/space prefix])]}"""
    out, cur, hunk = {}, None, None
    for line in text.split("\n"):
        if line.startswith("diff --git"):
            m = re.match(r"diff --git a/(.*) b/(.*)$", line)
            cur = m.group(2) if m else None
            hunk = None
            if cur:
                out.setdefault(cur, [])
            continue
        if line.startswith("--- ") or line.startswith("+++ "):
            if hunk is None:
                continue
        m = HUNK.match(line)
        if m and cur:
            hunk = (int(m.group(1)), [])
            out[cur].append(hunk)
            continue
        if hunk is not None and line[:1] in ("+", "-", " "):
            hunk[1].append(line)
    return out


def apply_hunks(old_lines, hunks):
    """Strict in-memory apply. Raises ValueError if anything doesn't match exactly."""
    new, pos = [], 0
    for start, lines in hunks:
        start = start - 1 if any(x[0] != "+" for x in lines) else start
        if start < pos or start > len(old_lines):
            raise ValueError("hunk out of order")
        new.extend(old_lines[pos:start])
        pos = start
        for x in lines:
            tag, body = x[0], x[1:]
            if tag in (" ", "-"):
                if pos >= len(old_lines) or old_lines[pos] != body:
                    raise ValueError("context mismatch")
                if tag == " ":
                    new.append(body)
                pos += 1
            else:
                new.append(body)
    new.extend(old_lines[pos:])
    return new


def _strip_docstrings(tree):
    import ast

    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            b = node.body
            if b and isinstance(b[0], ast.Expr) and isinstance(b[0].value, ast.Constant) and isinstance(b[0].value.value, str):
                node.body = b[1:] or [ast.Pass()]
    return tree


def _same_code(a, b):
    import types

    for attr in ("co_code", "co_names", "co_varnames", "co_freevars", "co_cellvars", "co_argcount",
                 "co_posonlyargcount", "co_kwonlyargcount", "co_flags", "co_name", "co_qualname",
                 "co_exceptiontable"):
        if getattr(a, attr) != getattr(b, attr):
            return False
    if len(a.co_consts) != len(b.co_consts):
        return False
    cls_body = "__firstlineno__" in a.co_names and "__firstlineno__" in b.co_names
    for x, y in zip(a.co_consts, b.co_consts):
        if (
            cls_body
            and type(x) is int
            and type(y) is int
            and x == a.co_firstlineno
            and y == b.co_firstlineno
        ):
            continue  # py3.13 stores the class's first line number as a constant
        if isinstance(x, types.CodeType) or isinstance(y, types.CodeType):
            if not (isinstance(x, types.CodeType) and isinstance(y, types.CodeType) and _same_code(x, y)):
                return False
        elif type(x) is not type(y) or repr(x) != repr(y):
            return False
    return True


def same_bytecode(old_src, new_src):
    import ast

    def comp(src):
        return compile(_strip_docstrings(ast.parse(src)), "<m>", "exec", dont_inherit=True)

    return _same_code(comp(old_src), comp(new_src))


def _ast_diffs(a, b, out):
    """Collect structural differences between two ASTs (stops after two)."""
    import ast

    if len(out) > 1:
        return
    if type(a) is not type(b):
        out.append(("x",))
    elif isinstance(a, ast.AST):
        if (
            isinstance(a, ast.Compare)
            and len(a.ops) == 1
            and len(b.ops) == 1
            and type(a.ops[0]) is not type(b.ops[0])
            and ast.dump(a.left) == ast.dump(b.left)
            and ast.dump(a.comparators[0]) == ast.dump(b.comparators[0])
        ):
            out.append(("cmp", a, b))
            return
        for f in a._fields:
            _ast_diffs(getattr(a, f), getattr(b, f), out)
    elif isinstance(a, list):
        if len(a) != len(b):
            out.append(("x",))
            return
        for x, y in zip(a, b):
            _ast_diffs(x, y, out)
    elif a != b:
        out.append(("str",) if isinstance(a, str) and isinstance(b, str) else ("x",))


def _op_name(node):
    import ast

    return {ast.Eq: "==", ast.NotEq: "!=", ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">=",
            ast.Is: "is", ast.IsNot: "is not", ast.In: "in", ast.NotIn: "not in"}.get(type(node))


class Mapper:
    def __init__(self, tests):
        m = json.loads(MAP.read_text())
        self.m = m
        by_id = {t["id"]: t["number"] for t in tests}
        num = [by_id.get(i) for i in m["ids"]]
        self.num = num
        self._inf = None
        self.sets = _LazySets(m["sets"], num)
        self.fixtures = {
            k: [num[i] for i in v if num[i] is not None] for k, v in m["fixtures"].items()
        }
        self.by_file = {}
        for t in tests:
            self.by_file.setdefault(t["file"], []).append(t["number"])
        self.all = [t["number"] for t in tests]
        self.cache = {}
        # runs `import sqlglot` in a subprocess, so coverage can't see what it touches
        self.lazy = [
            t["number"] for t in tests if t["id"].endswith("TestDialect::test_lazy_load")
        ]

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

    def in_def_header(self, f, line):
        """True when `line` is a def's header (decorators, signature) rather than its body."""
        best = None
        for a, b, cls, fb in self.m["spans"].get(f, ()):
            if a <= line <= b and (best is None or b - a < best[1] - best[0]):
                best = (a, b, cls, fb)
        return best is not None and best[2] == 0 and line < best[3]

    def is_class_level(self, f, line):
        """True when `line` is module level or directly in a class body (not inside a def)."""
        best = None
        for a, b, cls, _fb in self.m["spans"].get(f, ()):
            if a <= line <= b and (best is None or b - a < best[1] - best[0]):
                best = (a, b, cls)
        return best is None or best[2] == 1

    def attr(self):
        if getattr(self, "_attr", None) is None:
            try:
                d = json.loads(ATTR.read_text())
                d["importref"] = set(d["importref"])
                self._attr = d
            except Exception:
                self._attr = {"children": {}, "attrs": {}, "importref": set()}
        return self._attr

    def dialect_union(self, f):
        """Import-time attributes of a dialect file reach tests only through data flow:
        take every test that runs any line of that dialect's (or a sub-dialect's)
        dialect/parser/generator/typing files."""
        m = re.match(r"sqlglot/(?:dialects|parsers|generators|typing)/([^/]+)\.py$", f)
        if not m or m.group(1) in ("dialect", "__init__"):
            return ()
        name = m.group(1)
        key = ("dialect", name)
        if key not in self.cache:
            out = set()
            for n in [name] + list(self.attr()["children"].get(name, ())):
                for d in ("dialects", "parsers", "generators", "typing"):
                    g = f"sqlglot/{d}/{n}.py"
                    for i in self.m["lines"].get(g, {}).values():
                        out.update(self.sets[i])
            self.cache[key] = out
        return self.cache[key]

    def attr_tests(self, path, hunks):
        """One-line class attribute edit (NAME = value) in a dialect file: only tests that run a
        line referencing NAME AND use that dialect (or a sub-dialect). None -> use wide rules."""
        if not re.match(r"sqlglot/(dialects|parsers|generators|typing)/[^/]+\.py$", path):
            return None
        minus, plus = [], []
        for start, lines in hunks:
            old = start
            for x in lines:
                if x[0] == "-":
                    minus.append((old, x[1:])); old += 1
                elif x[0] == "+":
                    plus.append(x[1:])
                else:
                    old += 1
        if len(minus) != 1 or len(plus) != 1:
            return None
        pat = re.compile(r"^\s{4}([A-Z_][A-Z0-9_]*)\s*(?::[^=]+)?=\s")
        a, b = pat.match(minus[0][1]), pat.match(plus[0])
        if not a or not b or a.group(1) != b.group(1):
            return None
        name = a.group(1)
        at = self.attr()
        if name not in at["attrs"] or name in at["importref"] or not self.is_class_level(path, minus[0][0]):
            return None
        reach = {self.num[i] for i in at["attrs"][name] if self.num[i] is not None}
        return reach & set(self.dialect_union(path))

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
            if self.is_class_level(f, n):
                # module/class-body code runs at import: coverage credits whichever test imported
                # the module first, so widen to everything that uses the class / file
                out.update(self.func_union(f, n))
                out.update(self.dialect_union(f))
                out.update(self.lazy)
            elif self.in_def_header(f, n):
                out.update(self.func_union(f, n))  # default args / decorators / annotations
        for L in added:
            if self.is_class_level(f, max(L - 1, 1)):
                out.update(self.lazy)
            for k in (L - 1, L):
                out.update(self.tests_at(f, self.norm(f, k)))
            out.update(self.func_union(f, max(L - 1, 1)))
        return out

    def inf(self):
        if self._inf is None:
            try:
                d = json.loads(INF.read_text())
                d["sets"] = _LazySets(d["sets"], self.num)
                d["unprof"] = {self.num[i] for i in d.get("unprofiled", ()) if self.num[i] is not None}
                d["importset"] = set(d["import"])
                self._inf = d
            except Exception:
                self._inf = False
        return self._inf

    def analyze(self, path, hunks):
        """-> set of tests when the patch is provably harmless or a profiled single comparison
        swap (possibly empty); None when the normal coverage rules must decide."""
        import ast

        try:
            old = (SRC / path).read_text()
            new = "\n".join(apply_hunks(old.split("\n"), hunks))
            out = []
            tree_old = ast.parse(old)
            try:
                tree_new = ast.parse(new)
            except SyntaxError:
                # a broken module breaks every test that imports it
                if self.m["import"].get(path):
                    return set(self.all)
                allt = set()
                for i in self.m["lines"].get(path, {}).values():
                    allt.update(self.sets[i])
                return allt | set(self.lazy)
            _ast_diffs(tree_old, tree_new, out)
        except Exception:
            return None
        if not out:
            return set()  # identical AST: comments / whitespace / formatting only
        if all(d[0] == "str" for d in out):
            try:
                return set() if same_bytecode(old, new) else None  # docstring-only edits
            except Exception:
                return None
        if len(out) == 1 and out[0][0] == "x":
            return self.attr_tests(path, hunks)
        if len(out) != 1 or out[0][0] != "cmp":
            return None
        return self.infect_tests(path, out[0][1], out[0][2])

    def infect_tests(self, path, a, b):
        inf = self.inf()
        if not inf:
            return None
        try:
            key = f"{a.lineno}:{a.col_offset}"
            old_op, new_op = _op_name(a.ops[0]), _op_name(b.ops[0])
            known = inf["known"].get(path, {}).get(key)
            if known is None or known != old_op or new_op not in ALTS.get(old_op, ()):
                return None
            if f"{path}:{key}" in inf["importset"]:
                return None
            site = inf["sites"].get(path, {}).get(key)
            tests = set(inf["sets"][site["alts"][new_op]]) if site and new_op in site["alts"] else set()
            cov = self.tests_at(path, self.norm(path, a.lineno))
            tests |= {t for t in cov if t in inf["unprof"]}
            return tests
        except Exception:
            return None

    def structural_matters(self, text):
        """Deleted / renamed / re-moded files: harmless only for docs-like paths."""
        for m in re.finditer(r"^diff --git a/(.*) b/(.*)$", text, re.M):
            for path in (m.group(1), m.group(2)):
                if path.endswith((".md", ".rst", ".txt", ".png", ".jpg", ".svg")) or path.startswith(
                    ("posts/", "benchmarks/", "pdoc/", "sqlglot-integration-tests/")
                ):
                    continue
                return True
        return False

    def select(self, files, hunks=None):
        """-> set of test numbers, or None meaning 'run everything'."""
        out = set()
        for path, (removed, added) in files.items():
            if path in self.m["lines"]:
                if hunks and path in hunks:
                    got = self.analyze(path, hunks[path])
                    if got is not None:
                        out.update(got)
                        continue
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
            text = patch.read_text(errors="replace")
            sel = mp.select(parse_patch(text), split_hunks(text))
            if sel is not None and STRUCTURAL.search(text) and mp.structural_matters(text):
                sel = None
            chosen = mp.all if sel is None else sorted(sel)
        except Exception as e:  # never crash: fall back to everything
            print(f"{patch.stem}: {e!r}", file=sys.stderr)
            chosen = mp.all
        print(json.dumps({"commit": patch.stem, "workers": split(chosen, secs)}))


if __name__ == "__main__":
    main()
