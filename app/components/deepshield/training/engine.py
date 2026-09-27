import reflex as rx

import argparse
import hashlib
import importlib
import json
import logging
import random
from pathlib import Path
from app.components.deepshield.datasets.loaders import (
    load_sample,
    read_manifest,
    validate_splits,
)
from app.components.deepshield.datasets.robustness import RobustnessTransform
from app.components.deepshield.training.config import TrainingConfig


def seed_everything(seed: int):
    import numpy as np
    import torch

    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.set_num_threads(2)
    torch.use_deterministic_algorithms(True, warn_only=True)


def build_model(modality: str, config: TrainingConfig):
    module, symbol = config.factory.split(":", 1)
    return getattr(importlib.import_module(module), symbol)(modality, config)


def make_dataset(samples, root, encoder, transform=None):
    from torch.utils.data import Dataset

    class ManifestDataset(Dataset):
        def __len__(self):
            return len(samples)

        def __getitem__(self, index):
            sample = samples[index]
            return encoder(load_sample(sample, root, transform)), float(
                sample.label
            )

    return ManifestDataset()


def logits_for(model, loader):
    import torch

    labels, logits = [], []
    model.eval()
    with torch.inference_mode():
        for inputs, target in loader:
            output = model(inputs).reshape(-1)
            if not torch.isfinite(output).all():
                raise ValueError("Nonfinite validation logits")
            labels.extend(target.tolist())
            logits.extend(output.tolist())
    return labels, logits


def train(modality: str, config: TrainingConfig):
    import torch
    from torch.utils.data import DataLoader, WeightedRandomSampler

    seed_everything(config.seed)
    root = Path(config.dataset_root)
    samples = read_manifest(Path(config.manifest), root)
    validate_splits(samples)
    if any(s.modality != modality for s in samples):
        raise ValueError("Training manifest modality mismatch")
    train_rows = [s for s in samples if s.split == "train"]
    validation_rows = [s for s in samples if s.split == "validation"]
    model, encoder, collate, provenance = build_model(modality, config)
    model.cpu()
    transform = RobustnessTransform(config.augmentation)
    training = make_dataset(train_rows, root, encoder, transform)
    validation = make_dataset(validation_rows, root, encoder)
    generator = torch.Generator().manual_seed(config.seed)
    sampler = None
    if config.balance_classes:
        counts = {
            label: sum(s.label == label for s in train_rows) for label in (0, 1)
        }
        sampler = WeightedRandomSampler(
            [1 / counts[s.label] for s in train_rows],
            len(train_rows),
            generator=generator,
        )
    train_loader = DataLoader(
        training,
        batch_size=config.batch_size,
        sampler=sampler,
        shuffle=sampler is None,
        collate_fn=collate,
        num_workers=0,
        generator=generator,
    )
    val_loader = DataLoader(
        validation,
        batch_size=config.batch_size,
        collate_fn=collate,
        num_workers=0,
    )
    parameters = [p for p in model.parameters() if p.requires_grad]
    if not parameters:
        raise ValueError("No trainable parameters")
    optimizer = torch.optim.AdamW(
        parameters, lr=config.learning_rate, weight_decay=config.weight_decay
    )
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, patience=2, factor=0.5
    )
    loss_fn = torch.nn.BCEWithLogitsLoss()
    output = Path(config.output)
    output.mkdir(parents=True, exist_ok=True)
    best, stale = float("inf"), 0
    history = []
    for epoch in range(config.epochs):
        model.train()
        if config.freeze_backbone and hasattr(model, "features"):
            model.features.eval()
        total, seen = 0.0, 0
        for inputs, labels in train_loader:
            optimizer.zero_grad(set_to_none=True)
            # This runtime is CPU-only: full precision, no CUDA/AMP initialization.
            prediction = model(inputs).reshape(-1)
            loss = loss_fn(prediction, labels.float())
            if not torch.isfinite(loss):
                raise ValueError("Nonfinite training loss")
            loss.backward()
            torch.nn.utils.clip_grad_norm_(parameters, 1.0)
            optimizer.step()
            total += float(loss.detach()) * len(labels)
            seen += len(labels)
        labels, logits = logits_for(model, val_loader)
        validation_loss = float(
            loss_fn(torch.tensor(logits), torch.tensor(labels))
        )
        scheduler.step(validation_loss)
        entry = {
            "event": "epoch",
            "epoch": epoch + 1,
            "train_loss": total / seen,
            "validation_loss": validation_loss,
            "learning_rate": optimizer.param_groups[0]["lr"],
        }
        history.append(entry)
        logging.info(json.dumps(entry, allow_nan=False))
        torch.save(
            {
                "epoch": epoch + 1,
                "model": model.state_dict(),
                "optimizer": optimizer.state_dict(),
                "scheduler": scheduler.state_dict(),
            },
            output / "last.pt",
        )
        if validation_loss < best - config.min_delta:
            best, stale = validation_loss, 0
            torch.save(model.state_dict(), output / "best.pt")
            with (output / "best.pt").open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            with Path(config.manifest).open("rb") as stream:
                manifest_hash = hashlib.file_digest(
                    stream, "sha256"
                ).hexdigest()
            metadata = {
                "modality": modality,
                "epoch": epoch + 1,
                "validation_loss": best,
                "checkpoint_sha256": digest,
                "manifest_sha256": manifest_hash,
                "provenance": provenance,
                "config": config.model_dump(mode="json"),
                "calibrated": False,
                "labels": {
                    "0": "real_or_human",
                    "1": "synthetic_or_manipulated",
                },
                "training_datasets": sorted({s.dataset for s in train_rows}),
                "training_families": sorted(
                    {s.manipulation for s in train_rows}
                ),
            }
            (output / "best.metadata.json").write_text(
                json.dumps(metadata, indent=2, allow_nan=False)
            )
        else:
            stale += 1
        (output / "history.json").write_text(
            json.dumps(history, indent=2, allow_nan=False)
        )
        if stale >= config.patience:
            break
    return history


def main(modality: str):
    parser = argparse.ArgumentParser(
        description=f"DeepShield {modality} transfer training"
    )
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        config = TrainingConfig.model_validate_json(args.config.read_text())
        train(modality, config)
    except Exception as e:
        logging.exception(f"Error: {e}")
        raise
