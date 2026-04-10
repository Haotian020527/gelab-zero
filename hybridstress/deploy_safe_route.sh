#!/usr/bin/env bash
set -euo pipefail

STAGE="${1:-sanity}"
OUT_ROOT="${2:-results/safe_route}"

mkdir -p "${OUT_ROOT}"

case "${STAGE}" in
  sanity)
    python -m cockpit.safe_route_benchmark \
      --stage sanity \
      --output "${OUT_ROOT}/sanity"
    ;;
  routine)
    python -m cockpit.safe_route_benchmark \
      --stage routine \
      --runs 1 \
      --output "${OUT_ROOT}/routine"
    ;;
  safety)
    python -m cockpit.safe_route_benchmark \
      --stage safety \
      --output "${OUT_ROOT}/safety"
    ;;
  fallback)
    python -m cockpit.safe_route_benchmark \
      --stage fallback \
      --output "${OUT_ROOT}/fallback"
    ;;
  generalization)
    python -m cockpit.safe_route_benchmark \
      --stage generalization \
      --runs 1 \
      --output "${OUT_ROOT}/generalization"
    ;;
  token_accounting)
    python -m cockpit.safe_route_benchmark \
      --stage token_accounting \
      --output "${OUT_ROOT}/token_accounting"
    ;;
  dynamic_token_trace)
    python -m cockpit.safe_route_benchmark \
      --stage dynamic_token_trace \
      --output "${OUT_ROOT}/dynamic_token_trace"
    ;;
  stack)
    python -m cockpit.safe_route_benchmark \
      --stage stack \
      --stack-repeats 2 \
      --output "${OUT_ROOT}/stack"
    ;;
  all)
    python -m cockpit.safe_route_benchmark \
      --stage sanity \
      --output "${OUT_ROOT}/sanity"
    python -m cockpit.safe_route_benchmark \
      --stage routine \
      --runs 1 \
      --output "${OUT_ROOT}/routine"
    python -m cockpit.safe_route_benchmark \
      --stage safety \
      --output "${OUT_ROOT}/safety"
    python -m cockpit.safe_route_benchmark \
      --stage fallback \
      --output "${OUT_ROOT}/fallback"
    python -m cockpit.safe_route_benchmark \
      --stage generalization \
      --runs 1 \
      --output "${OUT_ROOT}/generalization"
    python -m cockpit.safe_route_benchmark \
      --stage token_accounting \
      --output "${OUT_ROOT}/token_accounting"
    python -m cockpit.safe_route_benchmark \
      --stage dynamic_token_trace \
      --output "${OUT_ROOT}/dynamic_token_trace"
    python -m cockpit.safe_route_benchmark \
      --stage stack \
      --stack-repeats 2 \
      --output "${OUT_ROOT}/stack"
    ;;
  *)
    echo "Usage: bash hybridstress/deploy_safe_route.sh [sanity|routine|safety|fallback|generalization|token_accounting|dynamic_token_trace|stack|all] [output_root]"
    exit 1
    ;;
esac
