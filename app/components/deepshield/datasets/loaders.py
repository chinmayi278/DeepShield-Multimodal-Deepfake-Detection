import reflex as rx

import hashlib
import json
import logging
from pathlib import Path
from typing import Literal
from app.components.deepshield.contracts import Contract, Field
from app.components.deepshield.config import Settings
from app.components.deepshield.media import (
    decode_audio,
    decode_image,
    private_media,
)


class Sample(Contract):
    id: str = Field(min_length=1)
    path: str = Field(min_length=1)
    modality: Literal["image", "video", "audio", "text", "multimodal"]
    label: int = Field(ge=0, le=1)
    dataset: str = Field(min_length=1)
    group: str = Field(min_length=1)
    subject: str = ""
    source_video: str = ""
    manipulation: str = "unknown"
    language: str = "und"
    sha256: str = ""
    split: Literal["", "train", "validation", "test"] = ""
    features: list[float] = Field(default_factory=list)


def safe_path(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError("Manifest path is outside dataset root or missing")
    return path


def read_manifest(path: Path, root: Path) -> list[Sample]:
    try:
        records = [
            Sample.model_validate_json(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        seen = set()
        for sample in records:
            if sample.id in seen:
                raise ValueError("Duplicate sample identity")
            seen.add(sample.id)
            with safe_path(root, sample.path).open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            if sample.sha256 and sample.sha256 != digest:
                raise ValueError("Manifest content hash mismatch")
            sample.sha256 = digest
        if not records:
            raise ValueError("Manifest is empty")
        return records
    except Exception as e:
        logging.exception(f"Error: {e}")
        raise


def connected_groups(samples: list[Sample]) -> list[int]:
    parent = list(range(len(samples)))

    def find(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    identities = {}
    labels = {}
    for index, sample in enumerate(samples):
        previous_label = labels.setdefault(sample.sha256, sample.label)
        if previous_label != sample.label:
            raise ValueError("Identical content has conflicting labels")
        keys = [("hash", sample.sha256), ("group", sample.group)]
        if sample.subject:
            keys.append(("subject", sample.subject))
        if sample.source_video:
            keys.append(("source_video", sample.source_video))
        for key in keys:
            if not key[1]:
                continue
            if key in identities:
                parent[find(index)] = find(identities[key])
            identities[key] = index
    return [find(index) for index in range(len(samples))]


def split_manifest(samples: list[Sample], seed: int = 42) -> list[Sample]:
    import numpy as np
    from sklearn.model_selection import StratifiedGroupKFold

    groups = np.asarray(connected_groups(samples))
    labels = np.asarray([sample.label for sample in samples])
    if len(set(groups)) < 5:
        raise ValueError(
            "At least five independent groups required; never fall back to random row splitting"
        )
    outer = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=seed)
    development, test = next(
        outer.split(np.zeros(len(samples)), labels, groups)
    )
    inner = StratifiedGroupKFold(n_splits=4, shuffle=True, random_state=seed)
    train_relative, val_relative = next(
        inner.split(
            np.zeros(len(development)), labels[development], groups[development]
        )
    )
    for name, indexes in (
        ("train", development[train_relative]),
        ("validation", development[val_relative]),
        ("test", test),
    ):
        if len(set(labels[indexes])) < 2:
            raise ValueError(
                "Cannot form class-balanced independent splits; collect more groups"
            )
        for index in indexes:
            samples[int(index)].split = name
    validate_splits(samples)
    return samples


def validate_splits(samples: list[Sample]):
    group_split = {}
    for group, sample in zip(connected_groups(samples), samples):
        if not sample.split:
            raise ValueError("Every sample needs a split")
        if group in group_split and group_split[group] != sample.split:
            raise ValueError(
                "Content, subject, source-video, or connected-group leakage"
            )
        group_split[group] = sample.split
    for name in ("train", "validation", "test"):
        if {s.label for s in samples if s.split == name} != {0, 1}:
            raise ValueError("Each split must contain both classes")


def write_manifest(samples: list[Sample], path: Path):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "\n".join(sample.model_dump_json() for sample in samples),
            encoding="utf-8",
        )
    except Exception as e:
        logging.exception(f"Error: {e}")
        raise


def load_sample(sample: Sample, root: Path, transform=None):
    import numpy as np
    from PIL import Image

    settings = Settings()
    try:
        path = safe_path(root, sample.path)
        if sample.modality == "multimodal":
            if not sample.features:
                raise ValueError(
                    "Fusion training requires held-out score/reliability/missingness features"
                )
            return np.asarray(sample.features, dtype=np.float32)
        if sample.modality == "text":
            text = path.read_text(encoding="utf-8")
            if not text.strip():
                raise ValueError("Empty original-language text")
            return text
        if path.stat().st_size > settings.max_media_bytes:
            raise ValueError("Dataset media exceeds decode limits")
        data = path.read_bytes()
        if transform:
            data = transform(data, sample.modality)
        if sample.modality == "image":
            return decode_image(data, settings)
        if sample.modality == "audio":
            return decode_audio(data, settings)
        import cv2

        with private_media(data) as temporary:
            capture = cv2.VideoCapture(temporary)
            try:
                count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
                fps = capture.get(cv2.CAP_PROP_FPS)
                if count < 2 or fps <= 0 or count / fps > settings.max_duration:
                    raise ValueError("Invalid dataset video duration")
                frames = []
                for index in np.linspace(0, count - 1, 8).astype(int):
                    capture.set(cv2.CAP_PROP_POS_FRAMES, int(index))
                    ok, frame = capture.read()
                    if (
                        not ok
                        or frame.shape[0] * frame.shape[1] > settings.max_pixels
                    ):
                        raise ValueError("Dataset video frame decode failed")
                    frames.append(
                        Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                    )
                return frames
            finally:
                capture.release()
    except Exception as e:
        logging.exception(f"Error: {e}")
        raise
