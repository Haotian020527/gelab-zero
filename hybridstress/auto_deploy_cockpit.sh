#!/bin/bash
# ============================================================================
# HybridStress Auto-Deploy Script — Cockpit Backend
# ============================================================================
# Runs the full experiment pipeline using the virtual cockpit backend.
# NO ADB / physical device required. All 20 tasks in cockpit IVI.
#
# Usage:
#   bash hybridstress/auto_deploy_cockpit.sh [stage]
#
# Stages:
#   all       - Full pipeline (default): sanity → M1 → M2
#   sync      - Only sync code
#   sanity    - Only cockpit M0 sanity check
#   full      - Only M1 (full benchmark)
#   detector  - Only M2 (CMV training)
#   transfer  - Only M3 (transfer eval with cockpit traces)
#   utility   - Only M4 (recovery study with cockpit)
# ============================================================================

set -e

# ─── Configuration ──────────────────────────────────────────────────────────
SSH_HOST="fce"
WORK_DIR="/home/fce/mnt/2T/Frank/LHT/gelab-zero-new"
CONDA_ACTIVATE='eval "$(/opt/conda/bin/conda shell.bash hook)" && conda activate gelab-zero'
STAGE="${1:-all}"
BACKEND="cockpit"

echo "============================================"
echo "HybridStress Cockpit Auto-Deploy"
echo "Backend: $BACKEND (virtual IVI)"
echo "Stage: $STAGE"
echo "Time: $(date)"
echo "============================================"

# ─── Helper functions ───────────────────────────────────────────────────────

ssh_exec() {
    local cmd="$1"
    ssh -o ConnectTimeout=10 "$SSH_HOST" "$cmd"
}

ssh_conda_exec() {
    local cmd="$1"
    ssh_exec "$CONDA_ACTIVATE && cd $WORK_DIR && $cmd"
}

check_server() {
    echo "[1/5] Checking server connectivity..."
    if ! ssh_exec "echo SERVER_OK" 2>/dev/null | grep -q "SERVER_OK"; then
        echo "ERROR: Cannot connect to server. Check tunnel."
        exit 1
    fi
    echo "  ✓ Server reachable"

    echo "[2/5] Checking GPU..."
    ssh_exec "nvidia-smi --query-gpu=name,memory.used,memory.total,utilization.gpu --format=csv,noheader"
    echo "  ✓ GPU check done"
}

sync_code() {
    echo "[3/5] Syncing code to server..."

    # Upload hybridstress module
    local HS_DIR="hybridstress"
    scp "$HS_DIR"/__init__.py \
        "$HS_DIR"/cmv_model.py \
        "$HS_DIR"/cmv_trainer.py \
        "$HS_DIR"/data_types.py \
        "$HS_DIR"/deploy.py \
        "$HS_DIR"/evaluator.py \
        "$HS_DIR"/fault_injector.py \
        "$HS_DIR"/gelab_integration.py \
        "$HS_DIR"/recovery.py \
        "$HS_DIR"/requirements.txt \
        "$HS_DIR"/run_benchmark.py \
        "$HS_DIR"/task_definitions.py \
        "$HS_DIR"/validators.py \
        "$HS_DIR"/vlm_judge.py \
        "$SSH_HOST:$WORK_DIR/hybridstress/"
    echo "  ✓ hybridstress/ synced (14 files)"

    # Upload cockpit module
    local CK_DIR="cockpit"
    ssh_exec "mkdir -p $WORK_DIR/cockpit/apps $WORK_DIR/cockpit/frontend"

    scp "$CK_DIR"/__init__.py \
        "$CK_DIR"/app.py \
        "$CK_DIR"/integration.py \
        "$CK_DIR"/screenshot.py \
        "$CK_DIR"/state.py \
        "$CK_DIR"/task_definitions.py \
        "$CK_DIR"/validators.py \
        "$SSH_HOST:$WORK_DIR/cockpit/"
    echo "  ✓ cockpit/ synced (7 files)"

    scp "$CK_DIR"/apps/__init__.py \
        "$CK_DIR"/apps/navigation.py \
        "$CK_DIR"/apps/media.py \
        "$CK_DIR"/apps/climate.py \
        "$CK_DIR"/apps/phone.py \
        "$CK_DIR"/apps/messages.py \
        "$CK_DIR"/apps/settings.py \
        "$CK_DIR"/apps/vehicle.py \
        "$SSH_HOST:$WORK_DIR/cockpit/apps/"
    echo "  ✓ cockpit/apps/ synced (8 files)"

    scp "$CK_DIR"/frontend/index.html \
        "$SSH_HOST:$WORK_DIR/cockpit/frontend/"
    echo "  ✓ cockpit/frontend/ synced"

    # Clear Python cache
    ssh_exec "rm -rf $WORK_DIR/hybridstress/__pycache__ $WORK_DIR/cockpit/__pycache__ $WORK_DIR/cockpit/apps/__pycache__" 2>/dev/null || true
    echo "  ✓ Cache cleared"
}

install_deps() {
    echo "[4/5] Installing dependencies (if needed)..."
    ssh_conda_exec "pip install fastapi uvicorn playwright requests numpy 2>&1 | tail -3" || true
    ssh_conda_exec "python -m playwright install chromium 2>&1 | tail -3" || true
    echo "  ✓ Dependencies checked"
}

deploy_stage() {
    local stage="$1"
    local session_name="hs_ck_${stage}"
    local output_dir="hybridstress_cockpit_${stage}"
    local extra_args="$2"
    local log_file="/tmp/${session_name}.log"

    echo "─────────────────────────────────────"
    echo "Deploying: $stage (screen: $session_name)"
    echo "─────────────────────────────────────"

    # Kill existing session if present
    ssh_exec "screen -S $session_name -X quit 2>/dev/null || true"

    # Launch in screen with cockpit backend
    ssh_exec "screen -dmS $session_name bash -c '
        $CONDA_ACTIVATE &&
        cd $WORK_DIR &&
        python -m hybridstress.run_benchmark --stage $stage --backend cockpit --output $output_dir $extra_args > $log_file 2>&1
    '"

    echo "  ✓ Launched in screen session: $session_name"
    echo "  Monitor: ssh $SSH_HOST \"screen -r $session_name\""
    echo "  Logs:    ssh $SSH_HOST \"tail -f $log_file\""

    # Wait and check it's still alive
    sleep 5
    local screen_out=$(ssh_exec "screen -ls | grep $session_name" 2>/dev/null || true)
    if echo "$screen_out" | grep -q "$session_name"; then
        echo "  ✓ Process is running"
        # Show first few lines of output
        echo "  Initial output:"
        ssh_exec "head -10 $log_file 2>/dev/null" || true
    else
        echo "  ⚠ Process may have exited. Log output:"
        ssh_exec "cat $log_file" 2>/dev/null || true
    fi
}

# ─── Main pipeline ──────────────────────────────────────────────────────────

check_server

if [ "$STAGE" = "sync" ]; then
    sync_code
    echo "Done. Code synced."
    exit 0
fi

sync_code
install_deps

case "$STAGE" in
    all)
        echo ""
        echo "═══════════════════════════════════════"
        echo " Full Cockpit Pipeline: sanity → M1 → M2"
        echo "═══════════════════════════════════════"

        # Stage 1: Cockpit sanity check (run synchronously, fast)
        echo ""
        echo "[5/5] Running cockpit sanity check..."
        ssh_conda_exec "cd $WORK_DIR && python -m hybridstress.run_benchmark --stage sanity --backend cockpit --output hybridstress_cockpit_sanity 2>&1" || {
            echo "ERROR: Cockpit sanity check failed!"
            echo "Check logs on server. Aborting."
            exit 1
        }
        echo "  ✓ Cockpit sanity PASSED"

        # Stage 2: M1 Full Benchmark (deploy in screen)
        echo ""
        echo "Deploying M1: Full Benchmark Construction (20 tasks × 10 conditions)..."
        deploy_stage "full" "--tasks 20 --seed 42"
        echo ""
        echo "  M1 deployed. Estimated: ~2-4 hours (cockpit is much faster than ADB)"
        echo ""
        echo "  After M1 completes, run:"
        echo "    bash hybridstress/auto_deploy_cockpit.sh detector"
        ;;
    sanity)
        echo ""
        echo "[5/5] Running cockpit sanity check..."
        ssh_conda_exec "cd $WORK_DIR && python -m hybridstress.run_benchmark --stage sanity --backend cockpit --output hybridstress_cockpit_sanity 2>&1"
        ;;
    full)
        deploy_stage "full" "--tasks 20 --seed 42"
        ;;
    detector)
        deploy_stage "detector" "--data hybridstress_cockpit_full"
        ;;
    transfer)
        deploy_stage "transfer" "--data hybridstress_cockpit_full"
        ;;
    utility)
        deploy_stage "utility" "--data hybridstress_cockpit_full"
        ;;
    *)
        echo "Unknown stage: $STAGE"
        echo "Usage: bash hybridstress/auto_deploy_cockpit.sh [all|sync|sanity|full|detector|transfer|utility]"
        exit 1
        ;;
esac

echo ""
echo "============================================"
echo "Deployment Summary"
echo "============================================"
echo "Backend: cockpit (virtual IVI — no ADB needed)"
echo "Check status: ssh $SSH_HOST 'screen -ls'"
echo "Check GPU:    ssh $SSH_HOST 'nvidia-smi'"
echo ""
echo "After experiments complete:"
echo "  → /monitor-experiment"
echo "  → /auto-review-loop \"HybridStress: modality-boundary failures in IVI\""
echo "============================================"
