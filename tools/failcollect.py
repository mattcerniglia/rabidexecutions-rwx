import json, os
_f = set()
def pytest_runtest_logreport(report):
    if report.outcome == "failed":
        _f.add(report.nodeid)
def pytest_unconfigure(config):
    if hasattr(config, "workerinput"):
        return
    json.dump(sorted(_f), open(os.environ["FAIL_OUT"], "w"))
