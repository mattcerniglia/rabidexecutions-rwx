pip install -q -r /kit/requirements.lock 2>&1 | grep -v -i 'notice\|warning'
cp -r /src /work && cd /work
mkdir -p /out/inf1
export PYTHONPATH=/work:/kit/tools SKIP_INTEGRATION=0 MAP_OUT=/out/inf1 SRC_ROOT=/work/sqlglot
python -m pytest -p infplugin tests/test_optimizer.py -k "test_eliminate_joins" -q --no-header -p no:cacheprovider -p no:randomly --timeout=600 2>&1 | tail -3
python - <<'P'
import json
d=json.load(open("/out/inf1/infect.json"))
print(len(d["sites"]),"sites", len(d["tests"]),"tests", len(d["import"]),"import-time sites")
for t,v in d["tests"].items(): print(t, len(v))
P
