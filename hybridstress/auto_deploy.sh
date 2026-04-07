#!/bin/bash
# ============================================================================
# HybridStress Auto-Deploy Script
# ============================================================================
# One-click deployment: sync → sanity → M1 (full) → M2 (detector) → M3 → M4
#
# Usage:
#   bash hybridstress/auto_deploy.sh [stage]
#
# Stages:
#   all       - Full pipeline (default)
#   sync      - Only sync code
#   full      - Only M1 (full benchmark)
#   detector  - Only M2 (CMV training)
#   transfer  - Only M3 (natural traces)
#   utility   - Only M4 (recovery study)
# ============================================================================

set -e

# ─── Configuration ──────────────────────────────────────────────────────────
SSH_HOST="fce"
WORK_DIR="/home/fce/mnt/2T/Frank/LHT/gelab-zero-new"
CONDA_ACTIVATE='eval "$(/opt/conda/bin/conda shell.bash hook)" && conda activate gelab-zero'
DEVICE_ID="192.168.50.174:5555"
STAGE="${1:-all}"

echo "============================================"
echo "HybridStress Auto-Deploy"
echo "Stage: $STAGE"
echo "Time: $(date)"
echo "============================================"

# ─── Helper functions ───────────────────────────────────────────────────────

ssh_exec() {
    local cmd="$1"
    local timeout="${2:-30}"
    ssh -o ConnectTimeout=10 "$SSH_HOST" "$cmd"
}

ssh_conda_exec() {
    local cmd="$1"
    ssh_exec "$CONDA_ACTIVATE && cd $WORK_DIR && $cmd" "${2:-30}"
}

check_server() {
    echo "[1/6] Checking server connectivity..."
    if ! ssh_exec "echo SERVER_OK" 2>/dev/null | grep -q "SERVER_OK"; then
        echo "ERROR: Cannot connect to server. Check cpolar tunnel."
        exit 1
    fi
    echo "  ✓ Server reachable"

    echo "[2/6] Checking GPU..."
    ssh_exec "nvidia-smi --query-gpu=name,memory.used,memory.total,utilization.gpu --format=csv,noheader"
    echo "  ✓ GPU check done"
}

check_adb() {
    echo "[3/6] Checking Android device..."
    local adb_out=$(ssh_exec "adb connect $DEVICE_ID && adb devices" 2>/dev/null)
    echo "$adb_out"
    if echo "$adb_out" | grep -q "$DEVICE_ID"; then
        echo "  ✓ ADB device connected"
        return 0
    else
        echo "  ⚠ ADB device NOT connected"
        echo "  Note: M1/M3/M4 require the Android device."
        echo "  M2 (detector) can run on previously collected data."
        return 1
    fi
}

sync_code() {
    echo "[4/6] Syncing code to server..."
    local LOCAL_DIR="hybridstress"

    # Upload all Python files and requirements.txt
    scp "$LOCAL_DIR"/__init__.py \
        "$LOCAL_DIR"/cmv_model.py \
        "$LOCAL_DIR"/cmv_trainer.py \
        "$LOCAL_DIR"/data_types.py \
        "$LOCAL_DIR"/deploy.py \
        "$LOCAL_DIR"/evaluator.py \
        "$LOCAL_DIR"/fault_injector.py \
        "$LOCAL_DIR"/gelab_integration.py \
        "$LOCAL_DIR"/recovery.py \
        "$LOCAL_DIR"/requirements.txt \
        "$LOCAL_DIR"/run_benchmark.py \
        "$LOCAL_DIR"/task_definitions.py \
        "$LOCAL_DIR"/validators.py \
        "$LOCAL_DIR"/vlm_judge.py \
        "$SSH_HOST:$WORK_DIR/hybridstress/"

    echo "  ✓ 14 files synced"

    # Clear Python cache to avoid stale bytecode
    ssh_exec "rm -rf $WORK_DIR/hybridstress/__pycache__" 2>/dev/null || true
    echo "  ✓ Cache cleared"
}

deploy_stage() {
    local stage="$1"
    local session_name="hs_${stage}"
    local output_dir="hybridstress_${stage}"
    local extra_args="$2"
    local log_file="/tmp/${session_name}.log"

    echo "─────────────────────────────────────"
    echo "Deploying M: $stage (screen: $session_name)"
    echo "─────────────────────────────────────"

    # Kill existing session if present
    ssh_exec "screen -S $session_name -X quit 2>/dev/null || true"

    # Launch in screen
    ssh_exec "screen -dmS $session_name bash -c '
        $CONDA_ACTIVATE &&
        cd $WORK_DIR &&
        python -m hybridstress.run_benchmark --stage $stage --output $output_dir $extra_args > $log_file 2>&1
    '"

    echo "  ✓ Launched in screen session: $session_name"
    echo "  Monitor: ssh $SSH_HOST \"screen -r $session_name\""
    echo "  Logs:    ssh $SSH_HOST \"tail -f $log_file\""

    # Wait a few seconds and check it's still alive
    sleep 3
    local screen_out=$(ssh_exec "screen -ls | grep $session_name" 2>/dev/null || true)
    if echo "$screen_out" | grep -q "$session_name"; then
        echo "  ✓ Process is running"
    else
        echo "  ⚠ Process may have exited. Check logs:"
        ssh_exec "tail -20 $log_file" 2>/dev/null || true
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

case "$STAGE" in
    all)
        ADB_OK=0
        check_adb && ADB_OK=1

        if [ "$ADB_OK" -eq 1 ]; then
            echo ""
            echo "[5/6] Deploying M1: Full Benchmark Construction..."
            deploy_stage "full" "--tasks 20 --seed 42"
            echo ""
            echo "  M1 deployed. Estimated: ~60 GPU-hours"
            echo "  After M1 completes, run: bash hybridstress/auto_deploy.sh detector"
        else
            echo ""
            echo "[5/6] ADB device unavailable, checking for existing M1 data..."
            EXISTING=$(ssh_exec "ls $WORK_DIR/hybridstress_benchmark/events/ 2>/dev/null | wc -l" 2>/dev/null || echo "0")
            echo "  Found $EXISTING event files from previous run"

            if [ "${EXISTING//[^0-9]/}" -gt "0" ]; then
                echo "  Existing data available. Deploying M2 (detector) directly..."
                deploy_stage "detector" "--data hybridstress_benchmark"
                echo "  M2 deployed. Estimated: ~6 GPU-hours"
            else
                echo "  No existing data. Cannot proceed without Android device."
                echo "  Connect the device and run: bash hybridstress/auto_deploy.sh full"
            fi
        fi
        ;;
    full)
        check_adb || { echo "ERROR: ADB device required for M1"; exit 1; }
        deploy_stage "full" "--tasks 20 --seed 42"
        ;;
    detector)
        deploy_stage "detector" "--data hybridstress_benchmark"
        ;;
    transfer)
        check_adb || { echo "WARNING: ADB device needed for natural trace collection"; }
        deploy_stage "transfer" "--data hybridstress_benchmark"
        ;;
    utility)
        check_adb || { echo "WARNING: ADB device needed for utility study"; }
        deploy_stage "utility" "--data hybridstress_benchmark"
        ;;
    *)
        echo "Unknown stage: $STAGE"
        echo "Usage: bash hybridstress/auto_deploy.sh [all|sync|full|detector|transfer|utility]"
        exit 1
        ;;
esac

echo ""
echo "============================================"
echo "[6/6] Deployment Summary"
echo "============================================"
echo "Check status: ssh $SSH_HOST 'screen -ls'"
echo "Check GPU:    ssh $SSH_HOST 'nvidia-smi'"
echo ""
echo "After experiments complete:"
echo "  → /monitor-experiment"
echo "  → /auto-review-loop \"HybridStress: modality-boundary failures\""
echo "============================================"
