import reflex as rx

import contextlib
import hashlib
import importlib
import logging
import re
import threading
from pathlib import Path
from typing import Protocol
from app.components.deepshield.config import Settings
from app.components.deepshield.contracts import Provenance, Result


class ModelUnavailable(RuntimeError):
    pass


class CheckpointAdapter(Protocol):
    """Trusted installed code only; implementations lazily load inside predict."""

    provenance: Provenance

    def predict(self, payload: object) -> Result: ...


def load_adapter(spec: str) -> CheckpointAdapter:
    module, symbol = spec.split(":", 1)
    adapter = getattr(importlib.import_module(module), symbol)()
    Provenance.model_validate(adapter.provenance)
    return adapter


class Registry:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._sessions: dict[str, tuple[object, Provenance]] = {}
        self._adapters: dict[str, CheckpointAdapter] = {}
        self._lock = threading.RLock()

    def adapter(self, spec: str) -> CheckpointAdapter:
        with self._lock:
            if spec not in self._adapters:
                with contextlib.suppress(ModelUnavailable, FileNotFoundError):
                    self._adapters[spec] = load_adapter(spec)
                    return self._adapters[spec]
                raise ModelUnavailable(
                    "checkpoint_unavailable_or_incompatible"
                ) from None
            return self._adapters[spec]

    def available_adapter(self, spec: str) -> CheckpointAdapter | None:
        with contextlib.suppress(ModelUnavailable, FileNotFoundError):
            return self.adapter(spec)
        return None

    def available_baseline(
        self, modality: str
    ) -> tuple[object, Provenance] | None:
        with contextlib.suppress(ModelUnavailable, FileNotFoundError):
            return self.baseline(modality)
        return None

    def baseline(self, modality: str) -> tuple[object, Provenance]:
        with self._lock:
            if modality in self._sessions:
                return self._sessions[modality]
            try:
                with contextlib.suppress(ModelUnavailable, FileNotFoundError):
                    result = self._load(modality)
                    self._sessions[modality] = result
                    return result
            except Exception as e:
                logging.exception(
                    f"Unexpected baseline checkpoint loading failure: {e}"
                )
            raise ModelUnavailable(
                "checkpoint_unavailable_or_incompatible"
            ) from None

    def _load(self, modality: str) -> tuple[object, Provenance]:
        import onnxruntime as ort
        from huggingface_hub import (
            HfApi,
            hf_hub_download,
            try_to_load_from_cache,
        )

        image = modality == "image"
        repo = (
            "buildborderless/CommunityForensics-DeepfakeDet-ViT"
            if image
            else "ayush2635/Dhwani-Multilingual-Deepfake-Audio-Detection-Model"
        )
        revision = (
            self.settings.image_revision
            if image
            else self.settings.audio_revision
        )
        filename = "onnx/model.onnx" if image else "best_model.onnx"
        local = (
            self.settings.image_local if image else self.settings.audio_local
        )
        expected = (
            self.settings.image_sha256 if image else self.settings.audio_sha256
        )
        if not re.fullmatch(r"[0-9a-f]{12,40}", revision):
            raise ModelUnavailable("Immutable commit revision required")
        if local:
            if not re.fullmatch(r"[0-9a-f]{64}", expected):
                raise ModelUnavailable("Local checkpoint requires SHA256")
            path = Path(local)
        else:
            cached = try_to_load_from_cache(repo, filename, revision=revision)
            if isinstance(cached, str):
                path = Path(cached)
            else:
                if not self.settings.allow_downloads:
                    raise ModelUnavailable(
                        "Downloads disabled; provision approved artifact"
                    )
                info = HfApi().model_info(
                    repo, revision=revision, files_metadata=True, timeout=15
                )
                artifact = next(
                    (s for s in info.siblings if s.rfilename == filename), None
                )
                if artifact is None:
                    raise ModelUnavailable("Checkpoint artifact missing")
                if (
                    info.private
                    or info.gated
                    or not artifact.size
                    or artifact.size > self.settings.download_budget
                ):
                    raise ModelUnavailable(
                        "Artifact exceeds download budget or is restricted"
                    )
                revision = info.sha
                path = Path(
                    hf_hub_download(
                        repo, filename, revision=revision, etag_timeout=15
                    )
                )
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if expected and digest != expected:
            raise ValueError("Checkpoint integrity mismatch")
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        session = ort.InferenceSession(
            str(path), sess_options=options, providers=["CPUExecutionProvider"]
        )
        inputs = session.get_inputs()
        if len(inputs) != 1 or inputs[0].type != "tensor(float)":
            raise ModelUnavailable("Unsupported ONNX input contract")
        shape = inputs[0].shape
        if image:
            expected = (3, 384, 384)
            if len(shape) != 4 or any(
                isinstance(dimension, int) and dimension != expected[index]
                for index, dimension in enumerate(shape[-3:])
            ):
                raise ModelUnavailable("Expected NCHW RGB 384 ONNX graph")
        if not image and (
            len(shape) != 2 or isinstance(shape[-1], int) and shape[-1] != 48000
        ):
            raise ModelUnavailable("Expected 48000-sample waveform graph")
        provenance = Provenance(
            model_id=repo,
            revision=revision,
            artifact_sha256=digest,
            license="MIT",
            runtime="onnxruntime/CPUExecutionProvider/fp32",
            calibrated=False,
            preprocessing="rgb-short-edge440-center384-clip-v1"
            if image
            else "mono16k-48000-zscore-v1",
            language_scope=[] if image else ["en", "hi", "ta", "te", "ml"],
        )
        return session, provenance

    def health(self) -> dict[str, str]:
        with self._lock:
            return {
                "image": "loaded"
                if "image" in self._sessions
                else "not_loaded",
                "audio": "loaded"
                if "audio" in self._sessions
                else "not_loaded",
                "text": "configured_not_verified"
                if self.settings.text_adapter
                else "unavailable",
                "temporal": "configured_not_verified"
                if self.settings.temporal_adapter
                else "frame_baseline_only",
                "fusion": "configured_not_verified"
                if self.settings.fusion_adapter
                else "calibrated_inputs_only",
            }
