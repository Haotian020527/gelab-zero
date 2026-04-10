#!/bin/bash
# HybridStress Cockpit Deployment Script
# ========================================
# Run this on the GPU server to execute all milestones with cockpit backend.
#
# Usage:
#   bash hybridstress/deploy_cockpit.sh [stage]
#   Stages: sanity | full | detector | transfer | utility | all | check_m2
#
# Prerequisites:
#   - conda env: gelab-zero
#   - pip install: fastapi uvicorn requests playwright
#   - playwright install chromium

set -e

STAGE=${1:-all}
WORK_DIR="/home/fce/mnt/2T/Frank/LHT/gelab-zero-new"
OUTPUT_DIR="$WORK_DIR/hybridstress_cockpit"
CONDA_ENV="gelab-zero"

# Activate conda
eval "$(/opt/conda/bin/conda shell.bash hook)" && conda activate $CONDA_ENV
cd "$WORK_DIR"

echo "============================================"
echo "HybridStress Cockpit — Stage: $STAGE"
echo "Output: $OUTPUT_DIR"
echo "============================================"

# Install cockpit dependencies if needed
pip install fastapi uvicorn requests 2>/dev/null || true
pip install playwright 2>/dev/null && playwright install chromium 2>/dev/null || true

run_sanity() {
    echo "[M0] Running cockpit sanity check..."
    python -m hybridstress.run_benchmark \
        --stage sanity \
        --backend cockpit \
        --output "$OUTPUT_DIR/sanity" \
        2>&1 | tee /tmp/hs_ck_m0.log
    echo "[M0] Done. Results: $OUTPUT_DIR/sanity/sanity_results.json"
}

run_full() {
    echo "[M1] Running full benchmark (20 tasks × 10 conditions)..."
    python -m hybridstress.run_benchmark \
        --stage full \
        --backend cockpit \
        --output "$OUTPUT_DIR/benchmark" \
        --tasks 20 \
        --seed 42 \
        2>&1 | tee /tmp/hs_ck_m1.log
    echo "[M1] Done. Results: $OUTPUT_DIR/benchmark/"
}

run_detector() {
    echo "[M2] Running detector training (VLM + CMV)..."
    python -m hybridstress.run_benchmark \
        --stage detector \
        --backend cockpit \
        --data "$OUTPUT_DIR/benchmark" \
        --output "$OUTPUT_DIR/benchmark" \
        --gpu_device cuda \
        --epochs 50 \
        --lr 1e-4 \
        --seed 42 \
        2>&1 | tee /tmp/hs_ck_m2.log
    echo "[M2] Done. Results: $OUTPUT_DIR/benchmark/detector/"
}

run_transfer() {
    echo "[M3] Running cockpit transfer evaluation..."
    python -m hybridstress.run_benchmark \
        --stage transfer \
        --backend cockpit \
        --data "$OUTPUT_DIR/benchmark" \
        --output "$OUTPUT_DIR/benchmark" \
        --gpu_device cuda \
        2>&1 | tee /tmp/hs_ck_m3.log
    echo "[M3] Done. Results: $OUTPUT_DIR/benchmark/transfer/"
}

run_utility() {
    echo "[M4] Running cockpit recovery utility..."
    python -m hybridstress.run_benchmark \
        --stage utility \
        --backend cockpit \
        --data "$OUTPUT_DIR/benchmark" \
        --output "$OUTPUT_DIR/benchmark" \
        --gpu_device cuda \
        2>&1 | tee /tmp/hs_ck_m4.log
    echo "[M4] Done. Results: $OUTPUT_DIR/benchmark/utility/"
}

check_m2() {
    echo "[CHECK] Checking M2 status..."
    if [ -f "$OUTPUT_DIR/benchmark/detector/detector_comparison.json" ]; then
        echo "M2 COMPLETE. Results:"
        cat "$OUTPUT_DIR/benchmark/detector/detector_comparison.json" | python -m json.tool 2>/dev/null || cat "$OUTPUT_DIR/benchmark/detector/detector_comparison.json"
    elif [ -f /tmp/hs_ck_m2.log ]; then
        echo "M2 still running. Last 20 lines:"
        tail -20 /tmp/hs_ck_m2.log
    else
        echo "M2 not started."
    fi
}

case $STAGE in
    sanity)     run_sanity ;;
    full)       run_full ;;
    detector)   run_detector ;;
    transfer)   run_transfer ;;
    utility)    run_utility ;;
    check_m2)   check_m2 ;;
    all)
        run_sanity
        run_full
        run_detector
        run_transfer
        run_utility
        echo "============================================"
        echo "ALL MILESTONES COMPLETE"
        echo "============================================"
        ;;
    m2_onwards)
        # Resume from M2 (M0+M1 already done)
        run_detector
        run_transfer
        run_utility
        echo "============================================"
        echo "M2-M4 COMPLETE"
        echo "============================================"
        ;;
    *)
        echo "Unknown stage: $STAGE"
        echo "Usage: bash hybridstress/deploy_cockpit.sh [sanity|full|detector|transfer|utility|all|check_m2|m2_onwards]"
        exit 1
        ;;
esac
