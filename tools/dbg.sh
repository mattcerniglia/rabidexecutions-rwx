pip install -q -r /kit/requirements.lock coverage 2>&1 | grep -v -i 'notice\|warning'
cp -r /src /work && cd /work
export PYTHONPATH=/work
cat > /tmp/t.py <<'P'
from sqlglot import parse_one
import sqlglot.optimizer.eliminate_joins as ej
from sqlglot.optimizer.qualify import qualify
sql="SELECT x.a FROM x LEFT JOIN (SELECT DISTINCT y.b FROM y) AS y ON x.b = y.b"
e=qualify(parse_one(sql), schema={"x":{"a":"int","b":"int"},"y":{"b":"int"}})
print(ej.eliminate_joins(e).sql())
P
python -m coverage run --source=/work/sqlglot/optimizer --data-file=/tmp/c.dat /tmp/t.py
python -m coverage report -m --data-file=/tmp/c.dat --include='*eliminate_joins.py'
