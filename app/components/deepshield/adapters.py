import reflex as rx

import contextlib
import hashlib
import json
import os
from pathlib import Path
from pydantic import ValidationError
from app.components.deepshield.registry import ModelUnavailable
from app.components.deepshield.contracts import (
    Contract,
    Evidence,
    Field,
    Provenance,
    Result,
)


class TextCheckpointConfig(Contract):
    local_directory: str
    repository: str
    revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    license: str
    weights_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    languages: list[str]
    validation_id: str = Field(min_length=1)
    fake_label_index: int = Field(default=1, ge=0, le=1)
    max_tokens: int = Field(default=512, ge=64, le=1024)
    min_characters: int = Field(default=100, ge=20)


class MultilingualCheckpoint:
    """Opt-in, locally provisioned safetensors; no remote code or implicit model download."""

    def __init__(self):
        config = None
        with contextlib.suppress(
            KeyError, FileNotFoundError, ValidationError, UnicodeError
        ):
            config_path = Path(os.environ["DEEPSHIELD_TEXT_CONFIG"])
            config = TextCheckpointConfig.model_validate_json(
                config_path.read_text()
            )
        if config is None:
            raise ModelUnavailable(
                "Text checkpoint configuration unavailable"
            ) from None
        self.config = config
        self.provenance = Provenance(
            model_id=self.config.repository,
            revision=self.config.revision,
            artifact_sha256=self.config.weights_sha256,
            license=self.config.license,
            runtime="transformers/CPU/float32",
            preprocessing="original-unicode-token-chunks-v1",
            language_scope=self.config.languages,
        )
        self._model = None
        self._tokenizer = None

    def _load(self):
        import torch
        from transformers import (
            AutoTokenizer,
            AutoModelForSequenceClassification,
        )

        if self._model is not None:
            return
        root = Path(self.config.local_directory)
        weights = root / "model.safetensors"
        if not weights.is_file() or weights.stat().st_size > 300 * 1024 * 1024:
            raise ModelUnavailable(
                "Provision a reviewed single-file checkpoint below 300 MB"
            )
        with weights.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if digest != self.config.weights_sha256:
            raise ValueError("Text checkpoint hash mismatch")
        self._tokenizer = AutoTokenizer.from_pretrained(
            root, local_files_only=True, trust_remote_code=False, use_fast=True
        )
        model = AutoModelForSequenceClassification.from_pretrained(
            root,
            local_files_only=True,
            trust_remote_code=False,
            use_safetensors=True,
            torch_dtype=torch.float32,
        )
        if model.config.num_labels != 2:
            raise ModelUnavailable("Binary sequence classifier required")
        self._model = model.cpu().eval()

    def predict(self, payload: object) -> Result:
        import torch
        import numpy as np

        self._load()
        text = payload["text"]
        language = payload["language"]
        if len(text.strip()) < self.config.min_characters:
            return Result(
                modality="text",
                reason="insufficient_text_for_validated_detector",
            )
        encoded = self._tokenizer(
            text, add_special_tokens=False, return_offsets_mapping=True
        )
        ids, offsets = encoded["input_ids"], encoded["offset_mapping"]
        capacity = (
            self.config.max_tokens
            - self._tokenizer.num_special_tokens_to_add(pair=False)
        )
        chunks = []
        scores = []
        for start in range(0, len(ids), capacity):
            end = min(start + capacity, len(ids))
            prepared = self._tokenizer.prepare_for_model(
                ids[start:end], return_tensors="pt", truncation=False
            )
            prepared = {
                key: value.unsqueeze(0) if value.ndim == 1 else value
                for key, value in prepared.items()
                if key in self._tokenizer.model_input_names
            }
            with torch.inference_mode():
                logits = self._model(**prepared).logits
                score = float(
                    torch.softmax(logits, dim=-1)[
                        0, self.config.fake_label_index
                    ]
                )
            if not np.isfinite(score):
                raise ValueError("Nonfinite text output")
            scores.append(score)
            chunks.append(
                Evidence(
                    kind="text_chunk",
                    score=score,
                    data={
                        "start_char": offsets[start][0],
                        "end_char": offsets[end - 1][1],
                        "coordinate_space": "python_unicode_codepoints",
                        "tokens": end - start,
                    },
                )
            )
        return Result(
            modality="text",
            status="degraded",
            score=float(np.median(scores)),
            score_semantics="median_uncalibrated_ai_origin_chunk_score",
            provenance=self.provenance,
            language=language,
            evidence=chunks,
            quality={
                "reliability": min(1.0, len(text) / 500),
                "chunks": float(len(chunks)),
                "disagreement": float(np.std(scores)),
            },
            warnings=[
                "Chunk aggregation is descriptive and not document-level calibration.",
                "AI origin is independent of factuality; passages are not translated.",
            ],
        )
