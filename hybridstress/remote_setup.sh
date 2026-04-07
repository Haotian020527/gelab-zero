#!/bin/bash
# Remote setup + sanity + M1 deploy — run ON the server
set -e

# Init conda
__conda_setup="$('/home/fce/miniconda3/bin/conda' 'shell.bash' 'hook' 2> /dev/null)"
eval "$__conda_setup"
conda activate gelab-zero

WORK=/home/fce/mnt/2T/Frank/LHT/gelab-zero-new
cd $WORK

echo "=== Installing dependencies ==="
pip install fastapi uvicorn requests numpy 2>&1 | tail -3
pip install playwright 2>&1 | tail -3 || true
python -m playwright install chromium 2>&1 | tail -3 || true

echo "=== Clearing Python cache ==="
rm -rf hybridstress/__pycache__ cockpit/__pycache__ cockpit/apps/__pycache__

echo "=== Running cockpit sanity check (M0) ==="
python -m hybridstress.run_benchmark --stage sanity --backend cockpit --output hybridstress_cockpit_sanity 2>&1

echo ""
echo "=== Sanity done. Checking results ==="
cat hybridstress_cockpit_sanity/sanity_results.json

echo ""
echo "=== Deploying M1: Full Benchmark (screen: hs_ck_full) ==="
# Kill any existing session
screen -S hs_ck_full -X quit 2>/dev/null || true

# Launch M1 in screen
screen -dmS hs_ck_full bash -c "
__conda_setup=\"\$('/home/fce/miniconda3/bin/conda' 'shell.bash' 'hook' 2> /dev/null)\"
eval \"\$__conda_setup\"
conda activate gelab-zero
cd $WORK
python -m hybridstress.run_benchmark --stage full --backend cockpit --output hybridstress_cockpit_full --tasks 20 --seed 42 > /tmp/hs_ck_full.log 2>&1
"

sleep 3
echo "=== Screen sessions ==="
screen -ls

echo ""
echo "=== Initial M1 output ==="
head -20 /tmp/hs_ck_full.log 2>/dev/null || echo "(waiting for output)"

echo ""
echo "=== DEPLOYMENT COMPLETE ==="
echo "Monitor: screen -r hs_ck_full"
echo "Logs: tail -f /tmp/hs_ck_full.log"
