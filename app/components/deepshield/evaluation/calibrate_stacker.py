import reflex as rx

import argparse
import hashlib
import json
import logging
from pathlib import Path
from app.components.deepshield.datasets.loaders import (
    connected_groups,
    read_manifest,
)
from app.components.deepshield.stacking import StackingArtifact
from app.components.deepshield.training.config import TrainingConfig


def main():
    parser = argparse.ArgumentParser(
        description="Fit Platt scaling on independent labeled stacking calibration data"
    )
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--calibration-manifest", required=True, type=Path)
    parser.add_argument("--calibration-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        import numpy as np
        import torch
        from sklearn.linear_model import LogisticRegression

        config = TrainingConfig.model_validate_json(args.config.read_text())
        development = read_manifest(
            Path(config.manifest), Path(config.dataset_root)
        )
        calibration = read_manifest(
            args.calibration_manifest, args.calibration_root
        )
        groups = connected_groups([*development, *calibration])
        if set(groups[: len(development)]) & set(groups[len(development) :]):
            raise ValueError(
                "Calibration overlaps training, model-selection, or final-test identities"
            )
        if any(
            s.modality != "multimodal" or len(s.features) != 20
            for s in calibration
        ):
            raise ValueError(
                "Expected versioned 20-feature multimodal observations"
            )
        labels = np.asarray([s.label for s in calibration])
        if set(labels) != {0, 1}:
            raise ValueError(
                "Both real and synthetic calibration observations required"
            )
        weights = torch.load(
            args.checkpoint, map_location="cpu", weights_only=True
        )
        coefficients = weights["linear.weight"].numpy().reshape(-1)
        intercept = float(weights["linear.bias"].item())
        features = np.asarray([s.features for s in calibration])
        logits = features @ coefficients + intercept
        scaler = LogisticRegression(random_state=config.seed).fit(
            logits[:, None], labels
        )
        with args.checkpoint.open("rb") as stream:
            checkpoint_hash = hashlib.file_digest(stream, "sha256").hexdigest()
        with args.calibration_manifest.open("rb") as stream:
            calibration_hash = hashlib.file_digest(stream, "sha256").hexdigest()
        artifact = StackingArtifact(
            coefficients=coefficients.tolist(),
            intercept=intercept,
            calibration_slope=float(scaler.coef_[0, 0]),
            calibration_intercept=float(scaler.intercept_[0]),
            calibration_id=calibration_hash,
            checkpoint_sha256=checkpoint_hash,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(artifact.model_dump_json(indent=2))
    except Exception as e:
        logging.exception(f"Error: {e}")
        raise


if __name__ == "__main__":
    main()
