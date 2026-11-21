pip install -q -r /kit/requirements.lock coverage 2>&1 | grep -v -i 'notice\|warning'
cp -r /src /work && cd /work
rm -rf /out/three && mkdir -p /out/three
export PYTHONPATH=/work:/kit/tools SKIP_INTEGRATION=0 MAP_OUT=/out/three
python -m pytest -p covplugin tests/test_optimizer.py tests/test_executor.py -q --no-header -p no:cacheprovider -p no:randomly --timeout=900 2>&1 | tail -5
python - <<'P'
import coverage, json
d=coverage.CoverageData("/out/cov.dat"); d.read()
d2=coverage.CoverageData("/out/three/cov.dat"); d2.read()
d.update(d2); d.write()
o=json.load(open("/out/opens.json")); o2=json.load(open("/out/three/opens.json"))
for k,v in o2.items(): o[k]=sorted(set(o.get(k,[]))|set(v))
json.dump(o,open("/out/opens.json","w"))
print("merged3")
P
