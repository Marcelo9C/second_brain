#!/usr/bin/env python3
"""Train an SMFP baseline attribution model from the dataset registry.

Usage:
    python scripts/train_smfp_baseline.py
    python scripts/train_smfp_baseline.py --algorithm logistic_regression
    python scripts/train_smfp_baseline.py --min-samples 5
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure project root is importable.
ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from app.schemas.smfp_training import SmfpBaselineTrainRequest  # noqa: E402
from app.services.smfp_training_service import SmfpTrainingService  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Train SMFP baseline model.")
    parser.add_argument(
        "--algorithm",
        choices=["random_forest", "logistic_regression"],
        default="random_forest",
        help="Classifier algorithm (default: random_forest).",
    )
    parser.add_argument(
        "--min-samples",
        type=int,
        default=3,
        help="Minimum samples per label (default: 3).",
    )
    args = parser.parse_args()

    service = SmfpTrainingService(
        dataset_registry_path=ROOT_DIR / "datasets" / "smfp" / "dataset_registry.json",
        model_registry_path=ROOT_DIR / "models" / "smfp" / "model_registry.json",
        model_dir=ROOT_DIR / "models" / "smfp",
    )

    request = SmfpBaselineTrainRequest(
        algorithm=args.algorithm,
        min_samples_per_label=args.min_samples,
    )

    try:
        result = service.train_baseline(request)
    except ValueError as exc:
        print(f"\n❌ Training failed:\n   {exc}", file=sys.stderr)
        return 1

    print("\n✅ Baseline model trained successfully!\n")
    print(json.dumps(result.model_dump(), indent=2, ensure_ascii=False))
    print(f"\n   Model ID:    {result.model_id}")
    print(f"   Algorithm:   {result.algorithm}")
    print(f"   Accuracy:    {result.accuracy:.4f}")
    print(f"   Macro F1:    {result.macro_f1:.4f}")
    print(f"   Samples:     {result.training_samples_used}")
    print(f"   Labels:      {result.labels_used}")
    print(f"   Status:      {result.status}")
    print(f"   Model file:  {result.model_path}")
    print(f"   Metadata:    {result.metadata_path}")
    print("\n⚠️  Baseline model is NOT promoted. active_model remains null.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
