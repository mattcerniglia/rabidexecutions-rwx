pip install -q -r /kit/requirements.lock 2>&1 | grep -v -i 'notice\|warning'
cp -r /src /work && cd /work
rm -rf /out/inf && mkdir -p /out/inf
export PYTHONPATH=/work:/kit/tools SKIP_INTEGRATION=0 MAP_OUT=/out/inf SRC_ROOT=/work/sqlglot
python -m pytest -p infplugin tests -q --no-header -p no:cacheprovider -p no:randomly --timeout=900 --deselect tests/test_parser.py::TestParser::test_max_nodes > /out/inf/pytest.log 2>&1
tail -4 /out/inf/pytest.log
echo infdone
