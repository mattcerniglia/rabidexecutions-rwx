"""pytest plugin: per-test line coverage of sqlglot + per-test file opens."""
import builtins, json, os, sys
import coverage

OUT = os.environ.get("MAP_OUT", "/out")
_cov = None
_cur = [""]
_opens = {}
_real_open = builtins.open


def _open(file, *a, **k):
    try:
        p = os.fspath(file) if not isinstance(file, int) else None
        if p and "fixtures" in str(p):
            _opens.setdefault(_cur[0], set()).add(os.path.abspath(p))
    except Exception:
        pass
    return _real_open(file, *a, **k)


def _patch_pool():
    import concurrent.futures as cf

    def submit(self, fn, /, *a, **k):
        f = cf.Future()
        init = getattr(self, "_initializer", None)
        if init is not None and not getattr(self, "_sync_init", False):
            self._sync_init = True
            init(*getattr(self, "_initargs", ()))
        try:
            f.set_result(fn(*a, **k))
        except BaseException as e:
            f.set_exception(e)
        return f

    cf.ThreadPoolExecutor.submit = submit
    cf.ProcessPoolExecutor.submit = submit
    import concurrent.futures.process as _p
    _p.ProcessPoolExecutor.submit = submit


def pytest_configure(config):
    global _cov
    _patch_pool()
    builtins.open = _open
    import io
    io.open = _open
    _cov = coverage.Coverage(data_file=os.path.join(OUT, "cov.dat"), source=["/work/sqlglot"], branch=False)
    _cov.erase()
    _cov.start()


import pytest


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(item, nextitem):
    _cur[0] = item.nodeid
    _cov.switch_context(item.nodeid)
    try:
        yield
    finally:
        _cur[0] = ""
        _cov.switch_context("")


def pytest_unconfigure(config):
    _cov.stop()
    _cov.save()
    json.dump({k: sorted(v) for k, v in _opens.items()}, open(os.path.join(OUT, "opens.json"), "w"))
