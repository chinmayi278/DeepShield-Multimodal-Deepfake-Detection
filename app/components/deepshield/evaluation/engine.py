import reflex as rx

import argparse
import hashlib
import json
import logging
from pathlib import Path
from app.components.deepshield.datasets.loaders import (
    connected_groups,
    read_manifest,
    validate_splits,
)
from app.components.deepshield.datasets.robustness import (
    Augmentation,
    RobustnessTransform,
)
from app.components.deepshield.evaluation.metrics import metrics
from app.components.deepshield.training.config import TrainingConfig
from app.components.deepshield.training.engine import (
    build_model,
    logits_for,
    make_dataset,
    seed_everything,
)


def evaluate(
    modality,
    config,
    checkpoint: Path,
    external_manifest: Path | None = None,
    external_root: Path | None = None,
    transforms: list[str] | None = None,
):
    import numpy as np
    import torch
    from torch.utils.data import DataLoader

    seed_everything(config.seed)
    root = Path(config.dataset_root)
    development = read_manifest(Path(config.manifest), root)
    validate_splits(development)
    if external_manifest:
        root = external_root or root
        samples = read_manifest(external_manifest, root)
        train = [s for s in development if s.split in {"train", "validation"}]
        joined = [*train, *samples]
        groups = connected_groups(joined)
        if set(groups[: len(train)]) & set(groups[len(train) :]):
            raise ValueError(
                "Cross-dataset evaluation overlaps development content or identities"
            )
        if {s.dataset for s in samples} & {s.dataset for s in train}:
            raise ValueError(
                "Cross-dataset evaluation requires distinct dataset identities"
            )
    else:
        samples = [s for s in development if s.split == "test"]
    if not samples or any(s.modality != modality for s in samples):
        raise ValueError("Empty or modality-incompatible evaluation manifest")
    metadata_path = checkpoint.parent / "best.metadata.json"
    metadata = json.loads(metadata_path.read_text())
    with checkpoint.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if (
        digest != metadata["checkpoint_sha256"]
        or metadata["modality"] != modality
    ):
        raise ValueError("Evaluation checkpoint provenance mismatch")
    model, encoder, collate, provenance = build_model(modality, config)
    model.load_state_dict(
        torch.load(checkpoint, map_location="cpu", weights_only=True)
    )
    model.cpu().eval()
    reports = {}
    for name in transforms or ["none"]:
        transform = RobustnessTransform(
            Augmentation(
                name=name,
                seed=config.seed,
                severity=config.augmentation.severity,
                background_audio=config.augmentation.background_audio,
            )
        )
        loader = DataLoader(
            make_dataset(samples, root, encoder, transform),
            batch_size=config.batch_size,
            collate_fn=collate,
            num_workers=0,
        )
        labels, logits = logits_for(model, loader)
        scores = (1 / (1 + np.exp(-np.clip(logits, -80, 80)))).tolist()
        report = {
            "overall": metrics(
                labels, scores, config.threshold, modality == "audio"
            ),
            "subsets": {},
        }
        for field in ("dataset", "language", "manipulation"):
            report["subsets"][field] = {}
            for value in sorted({getattr(s, field) for s in samples}):
                indexes = [
                    i
                    for i, s in enumerate(samples)
                    if getattr(s, field) == value
                ]
                report["subsets"][field][value] = metrics(
                    [int(labels[i]) for i in indexes],
                    [scores[i] for i in indexes],
                    config.threshold,
                    modality == "audio",
                )
        unseen = [
            i
            for i, s in enumerate(samples)
            if s.manipulation not in metadata["training_families"]
            and s.manipulation != "unknown"
        ]
        report["unseen_manipulations"] = (
            metrics(
                [int(labels[i]) for i in unseen],
                [scores[i] for i in unseen],
                config.threshold,
                modality == "audio",
            )
            if unseen
            else {
                "status": "unavailable",
                "reason": "no_unseen_labeled_families",
            }
        )
        reports[name] = report
    return {
        "modality": modality,
        "checkpoint_sha256": digest,
        "cross_dataset": bool(external_manifest),
        "seed": config.seed,
        "score_semantics": "uncalibrated_detector_score",
        "threshold_validation_id": config.threshold_validation_id,
        "threshold_warning": "Threshold is experimental unless a separate held-out validation identity is supplied.",
        "reports": reports,
        "provenance": provenance,
    }


def main(modality: str):
    parser = argparse.ArgumentParser(
        description=f"Measured {modality} evaluation; no sample predictions"
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--external-manifest", type=Path)
    parser.add_argument("--external-root", type=Path)
    parser.add_argument("--transforms", nargs="+", default=["none"])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        config = TrainingConfig.model_validate_json(args.config.read_text())
        report = evaluate(
            modality,
            config,
            args.checkpoint,
            args.external_manifest,
            args.external_root,
            args.transforms,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, allow_nan=False))
        logging.info(
            json.dumps({"event": "evaluation_complete", "modality": modality})
        )
    except Exception as e:
        logging.exception(f"Error: {e}")
        raise
