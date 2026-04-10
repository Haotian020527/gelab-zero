"""
HybridStress: Modality-Boundary Fault Injection & Evaluation Framework
=====================================================================

Core module for the HybridStress benchmark. Provides:
1. SwitchEvent data structure for recording modality-boundary events
2. Fault injection wrapper for mcp_backend_implements.py
3. Deterministic validators (ADB, UI XML, OCR)
4. Counterfactual 3-branch replay protocol
5. Cross-Modal Verifier (CMV) reference detector
6. Evaluation pipeline (prevalence, detector comparison, transfer, recovery)

Usage:
    # Sanity check
    python -m hybridstress.run_benchmark --stage sanity --output hybridstress_sanity/

    # Full benchmark
    python -m hybridstress.run_benchmark --stage full --output benchmark_data/

    # CMV training
    python -m hybridstress.cmv_trainer --data_dir benchmark_data/events/ --output_dir models/cmv/

    # VLM judge
    python -m hybridstress.vlm_judge --events_dir benchmark_data/events/ --output vlm_scores.json

    # Deploy to server
    python -m hybridstress.deploy --action sync
    python -m hybridstress.deploy --action run --stage sanity
"""

__version__ = "0.2.0"
__author__ = "HybridStress Team"
