#!/bin/bash
# Deploy M2: Detector Training (VLM judge → CMV → Eval)
set -e

__conda_setup="$('/home/fce/miniconda3/bin/conda' 'shell.bash' 'hook' 2> /dev/null)"
eval "$__conda_setup"
conda activate gelab-zero

WORK=/home/fce/mnt/2T/Frank/LHT/gelab-zero-new
cd $WORK

echo "============================================"
echo "HybridStress M2: Detector Training Pipeline"
echo "Time: $(date)"
echo "============================================"

# Check M1 completed
if [ ! -f hybridstress_cockpit_full/prevalence_results.json ]; then
    echo "ERROR: M1 not found. Run M1 first."
    exit 1
fi
echo "✓ M1 data found"

# Check GPU
nvidia-smi --query-gpu=name,memory.used,memory.total --format=csv,noheader
echo ""

# Kill any existing M2 session
tmux kill-session -t hs_ck_m2 2>/dev/null || true

# Deploy M2 in tmux
tmux new-session -d -s hs_ck_m2 "
__conda_setup=\"\$('/home/fce/miniconda3/bin/conda' 'shell.bash' 'hook' 2> /dev/null)\"
eval \"\$__conda_setup\"
conda activate gelab-zero
cd $WORK
echo '=== M2 Starting: $(date) ==='
python -m hybridstress.run_benchmark \
    --stage detector \
    --backend cockpit \
    --data hybridstress_cockpit_full \
    --output hybridstress_cockpit_models \
    --seed 42 \
    2>&1 | tee /tmp/hs_ck_m2.log
echo '=== M2 Finished: \$(date) ==='
"

sleep 3

echo "=== Tmux sessions ==="
tmux ls

echo ""
echo "=== Initial M2 output ==="
head -20 /tmp/hs_ck_m2.log 2>/dev/null || echo "(waiting for output)"

echo ""
echo "=== M2 DEPLOYED ==="
echo "Monitor: tmux attach -t hs_ck_m2"
echo "Logs:    tail -f /tmp/hs_ck_m2.log"
echo "Expected: ~6 GPU-hrs (VLM 4h + CMV 2h)"
