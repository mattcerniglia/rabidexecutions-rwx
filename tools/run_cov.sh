set -e
pip install -q -r /kit/requirements.lock coverage 2>&1 | tail -2
cp -r /src /work && cd /work
export PYTHONPATH=/work:/kit/tools SKIP_INTEGRATION=0 MAP_OUT=/out
python -m pytest -p covplugin tests -q --no-header -p no:cacheprovider -p no:randomly --timeout=300 -rA 2>&1 > /out/pytest.log || true
tail -5 /out/pytest.log
