pip install -q -r /kit/requirements.lock coverage 2>&1 | grep -v -i 'notice\|warning'
cp -r /src /work && cd /work
export PYTHONPATH=/work:/kit/tools SKIP_INTEGRATION=0 MAP_OUT=/out/one
python -m pytest -p covplugin tests/test_optimizer.py -k "test_eliminate_joins" -q --no-header -p no:cacheprovider 2>&1 | tail -3
python - <<'P'
import coverage
d=coverage.CoverageData("/out/one/cov.dat"); d.read()
f="/work/sqlglot/optimizer/eliminate_joins.py"
c=d.contexts_by_lineno(f)
print({k:v for k,v in c.items() if 55<=k<=70})
P
