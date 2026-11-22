pip install -q -r /kit/requirements.lock coverage 2>&1 | grep -v -i 'notice\|warning'
cp -r /src /work && cd /work
rm -rf /out/cov2 && mkdir -p /out/cov2
export PYTHONPATH=/work:/kit/tools SKIP_INTEGRATION=0 MAP_OUT=/out/cov2
python -m pytest -p covplugin tests -q --no-header -p no:cacheprovider -p no:randomly --timeout=900 --deselect tests/test_parser.py::TestParser::test_max_nodes > /out/cov2/pytest.log 2>&1
tail -4 /out/cov2/pytest.log
python - <<'P'
import coverage
d=coverage.CoverageData("/out/cov2/cov.dat"); d.read()
sc=[c for c in d.measured_contexts() if c.startswith("SCOPE::")]
print("scope contexts:", len(sc), sc[:6])
P
echo cov2done
