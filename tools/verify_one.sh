pip install -q -r /kit/requirements.lock 2>&1 | grep -v -i 'notice\|warning'
cp -r /src /work && cd /work
export PYTHONPATH=/work SKIP_INTEGRATION=0
python - <<'P'
import json
m=json.load(open("/kit/mut/meta.json"))["m015"]
p="/work/"+m["file"]; L=open(p).read().split("\n"); assert L[m["line"]-1]==m["old"]; L[m["line"]-1]=m["new"]; open(p,"w").write("\n".join(L))
P
python -m pytest "tests/test_executor.py::TestExecutor::test_execute_tpcds" -q --no-header -p no:cacheprovider -p no:randomly --timeout=900 2>&1 | tail -3
