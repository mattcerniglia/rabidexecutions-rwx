"""pytest plugin: state-infection profiling of pristine sqlglot.

Rewrites every single-operator Compare in sqlglot into a probe call that returns the
ORIGINAL result and records, per test, which alternative operators would have produced
a different value on the same operands. Nothing here ever runs a mutant.
"""
import ast, builtins, importlib.abc, importlib.machinery, json, operator, os, sys
import pytest

OUT = os.environ.get("MAP_OUT", "/out")
ROOT = os.environ.get("SRC_ROOT", "/work/sqlglot")

OPS = {
    "==": operator.eq, "!=": operator.ne, "<": operator.lt, "<=": operator.le,
    ">": operator.gt, ">=": operator.ge, "is": operator.is_, "is not": operator.is_not,
    "in": lambda a, b: operator.contains(b, a), "not in": lambda a, b: not operator.contains(b, a),
}
AST_OP = {ast.Eq: "==", ast.NotEq: "!=", ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">=",
          ast.Is: "is", ast.IsNot: "is not", ast.In: "in", ast.NotIn: "not in"}
ALTS = {
    "==": ["!=", "is"], "!=": ["==", "is not"], "<": ["<=", ">", ">="], "<=": ["<", ">", ">="],
    ">": [">=", "<", "<="], ">=": [">", "<", "<="], "is": ["is not", "=="], "is not": ["is", "!="],
    "in": ["not in"], "not in": ["in"],
}
SITES = []          # site id -> (file, line, col, op)
_cur = [""]
_masks = {}         # test -> {site: {alt: True}}
_ctx_import = set()  # sites reached outside any test (import time)
_SAFE_CONTAINER = (list, tuple, set, frozenset, dict, str, bytes, range)


def _probe(sid, a, b):
    op = SITES[sid][3]
    r = OPS[op](a, b)
    if _cur[0] == "":
        _ctx_import.add(sid)
    d = _masks.setdefault(_cur[0], {}).setdefault(sid, set())
    if len(d) == len(ALTS[op]):
        return r
    for alt in ALTS[op]:
        if alt in d:
            continue
        if alt in ("in", "not in") or op in ("in", "not in"):
            if not isinstance(b, _SAFE_CONTAINER):
                d.add(alt)  # unknown iterator/container semantics: treat as infected, never consume it
                continue
        try:
            if OPS[alt](a, b) != r:
                d.add(alt)
        except Exception:
            d.add(alt)
    if _cur[0] == "":
        _ctx_import.add(sid)
    return r


class _Rewrite(ast.NodeTransformer):
    def __init__(self, rel):
        self.rel = rel

    def visit_Compare(self, node):
        self.generic_visit(node)
        if len(node.ops) == 1 and type(node.ops[0]) in AST_OP:
            op = AST_OP[type(node.ops[0])]
            SITES.append((self.rel, node.lineno, node.col_offset, op))
            call = ast.Call(
                func=ast.Name("_sgp_", ast.Load()),
                args=[ast.Constant(len(SITES) - 1), node.left, node.comparators[0]],
                keywords=[],
            )
            return ast.copy_location(call, node)
        return node


class _Loader(importlib.machinery.SourceFileLoader):
    def get_code(self, fullname):
        path = self.get_filename(fullname)
        src = self.get_data(path)
        tree = ast.parse(src, path)
        rel = os.path.relpath(path, os.path.dirname(ROOT))
        tree = ast.fix_missing_locations(_Rewrite(rel).visit(tree))
        return compile(tree, path, "exec", dont_inherit=True)


class _Finder(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if not (name == "sqlglot" or name.startswith("sqlglot.")):
            return None
        spec = importlib.machinery.PathFinder.find_spec(name, path)
        if spec and isinstance(spec.loader, importlib.machinery.SourceFileLoader) and spec.origin \
                and os.path.abspath(spec.origin).startswith(ROOT):
            spec.loader = _Loader(spec.loader.name, spec.loader.path)
        return spec


def _patch_pool():
    import concurrent.futures as cf, pickle

    def submit(self, fn, /, *a, **k):
        f = cf.Future()
        init = getattr(self, "_initializer", None)
        if init is not None and not getattr(self, "_sync_init", False):
            self._sync_init = True
            init(*getattr(self, "_initargs", ()))
        try:
            fn, a, k = pickle.loads(pickle.dumps((fn, a, k)))
            f.set_result(pickle.loads(pickle.dumps(fn(*a, **k))))
        except BaseException as e:
            f.set_exception(e)
        return f

    cf.ThreadPoolExecutor.submit = submit
    cf.ProcessPoolExecutor.submit = submit
    import concurrent.futures.process as _p
    _p.ProcessPoolExecutor.submit = submit


def pytest_configure(config):
    sys.dont_write_bytecode = True
    builtins._sgp_ = _probe
    for m in [m for m in sys.modules if m == "sqlglot" or m.startswith("sqlglot.")]:
        del sys.modules[m]
    sys.meta_path.insert(0, _Finder())
    _patch_pool()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(item, nextitem):
    _cur[0] = item.nodeid
    try:
        yield
    finally:
        _cur[0] = ""


def pytest_unconfigure(config):
    out = {"sites": SITES, "import": sorted(_ctx_import), "tests": {}}
    for t, per in _masks.items():
        if t == "":
            continue
        out["tests"][t] = {str(s): sorted(alts) for s, alts in per.items() if alts}
    json.dump(out, open(os.path.join(OUT, "infect.json"), "w"), separators=(",", ":"))
