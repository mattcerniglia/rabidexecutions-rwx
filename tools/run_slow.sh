pip install -q -r /kit/requirements.lock coverage 2>&1 | grep -v -i 'notice\|warning'
cp -r /src /work && cd /work
mkdir -p /out/two
export PYTHONPATH=/work:/kit/tools SKIP_INTEGRATION=0 MAP_OUT=/out/two
python -m pytest -p covplugin tests -q --no-header -p no:cacheprovider -p no:randomly --timeout=900 -k "test_execute_tpcds or (TestOptimizer and test_tpcds) or test_max_nodes or test_generator_memory or test_execute_tpch or test_optimized_tpch" 2>&1 | tail -5
python - <<'P'
import coverage, json
d=coverage.CoverageData("/out/cov.dat"); d.read()
d2=coverage.CoverageData("/out/two/cov.dat"); d2.read()
d.update(d2); d.write()
o=json.load(open("/out/opens.json")); o2=json.load(open("/out/two/opens.json"))
for k,v in o2.items(): o[k]=sorted(set(o.get(k,[]))|set(v))
json.dump(o,open("/out/opens.json","w"))
print("merged")
P
