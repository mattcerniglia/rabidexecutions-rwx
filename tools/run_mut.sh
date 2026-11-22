pip install -q -r /kit/requirements.lock 2>&1 | grep -v -i 'notice\|warning'
cp -r /src /work && cd /work
mkdir -p /out/${RES:-mutres}
export PYTHONPATH=/work:/kit/tools SKIP_INTEGRATION=0
python - <<'P' > /tmp/list.txt
import json
for k,v in json.load(open("/kit/${MUTDIR:-mut}/meta.json")).items(): print(k, v["file"], v["line"])
P
while read cid f line; do
  [ -f /out/${RES:-mutres}/$cid.json ] && continue
  cp /src/$f /tmp/orig.py
  python - "$cid" <<'P'
import json,sys
m=json.load(open("/kit/${MUTDIR:-mut}/meta.json"))[sys.argv[1]]
p="/work/"+m["file"]; L=open(p).read().split("\n"); assert L[m["line"]-1]==m["old"]; L[m["line"]-1]=m["new"]; open(p,"w").write("\n".join(L))
P
  s=$(date +%s)
  FAIL_OUT=/out/${RES:-mutres}/$cid.json python -m pytest -p failcollect tests -q --no-header -p no:cacheprovider -p no:randomly --timeout=240 --deselect tests/test_parser.py::TestParser::test_max_nodes > /out/${RES:-mutres}/$cid.log 2>&1
  echo "$cid $f $line $(( $(date +%s)-s ))s" >> /out/${RES:-mutres}/progress.txt
  cp /tmp/orig.py /work/$f
done < /tmp/list.txt
echo allmutdone >> /out/${RES:-mutres}/progress.txt
