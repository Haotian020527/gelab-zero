#!/bin/bash
# Deploy M1 full benchmark in tmux — run ON the server
set -e

__conda_setup="$('/home/fce/miniconda3/bin/conda' 'shell.bash' 'hook' 2> /dev/null)"
eval "$__conda_setup"
conda activate gelab-zero

WORK=/home/fce/mnt/2T/Frank/LHT/gelab-zero-new
cd $WORK

echo "=== Deploying M1: Full Benchmark (tmux: hs_ck_full) ==="

# Kill any existing session
tmux kill-session -t hs_ck_full 2>/dev/null || true

# Launch M1 in tmux
tmux new-session -d -s hs_ck_full "
__conda_setup=\"\$('/home/fce/miniconda3/bin/conda' 'shell.bash' 'hook' 2> /dev/null)\"
eval \"\$__conda_setup\"
conda activate gelab-zero
cd $WORK
python -m hybridstress.run_benchmark --stage full --backend cockpit --output hybridstress_cockpit_full --tasks 20 --seed 42 2>&1 | tee /tmp/hs_ck_full.log
"

sleep 3

echo "=== Tmux sessions ==="
tmux ls

echo ""
echo "=== Initial M1 output ==="
head -20 /tmp/hs_ck_full.log 2>/dev/null || echo "(waiting for output)"

echo ""
echo "=== DEPLOYMENT COMPLETE ==="
echo "Monitor: tmux attach -t hs_ck_full"
echo "Logs:    tail -f /tmp/hs_ck_full.log"
