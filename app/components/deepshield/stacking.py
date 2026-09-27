import reflex as rx

import hashlib
import logging
import math
import os
from pathlib import Path
from app.components.deepshield.contracts import (
    Contract,
    Field,
    Provenance,
    Result,
)


class StackingArtifact(Contract):
    coefficients: list[float] = Field(min_length=20, max_length=20)
    intercept: float
    calibration_slope: float
    calibration_intercept: float
    calibration_id: str = Field(min_length=1)
    checkpoint_sha256: str
    schema_version: str = "score-available-quality-calibrated-missing-v1"
    license: str = "team-supplied"


def feature_vector(features: dict) -> list[float]:
    values = []
    for modality in ("image", "video", "audio", "text"):
        item = features["modalities"][modality]
        values.extend(
            [
                float(item["score"])
                if item["available"] and item["score"] is not None
                else 0.0,
                float(item["available"]),
                float(item["quality"]),
                float(item["calibrated"]),
                float(item["missing"]),
            ]
        )
    return values


class CalibratedStacker:
    def __init__(self):
        try:
            raw = Path(os.environ["DEEPSHIELD_STACKING_ARTIFACT"]).read_bytes()
            self.artifact = StackingArtifact.model_validate_json(raw)
        except Exception as e:
            logging.exception(f"Error: {e}")
            raise
        self.provenance = Provenance(
            model_id="deepshield/team-logistic-stacker",
            revision=self.artifact.checkpoint_sha256,
            artifact_sha256=hashlib.sha256(raw).hexdigest(),
            license=self.artifact.license,
            runtime="python/cpu",
            preprocessing=self.artifact.schema_version,
            calibrated=True,
            calibration_id=self.artifact.calibration_id,
        )

    def predict(self, payload: object) -> Result:
        artifact = self.artifact
        values = feature_vector(payload)
        if not any(
            payload["modalities"][m]["available"]
            for m in ("image", "video", "audio", "text")
        ):
            return Result(modality="fusion", reason="no_available_modalities")
        logit = (
            sum(a * b for a, b in zip(artifact.coefficients, values))
            + artifact.intercept
        )
        calibrated = (
            artifact.calibration_slope * logit + artifact.calibration_intercept
        )
        score = 1 / (1 + math.exp(-max(-80, min(80, calibrated))))
        return Result(
            modality="fusion",
            status="ok",
            score=score,
            score_semantics="heldout_calibrated_stacking_score",
            provenance=self.provenance,
            quality={"disagreement": float(payload["disagreement"])},
            warnings=[
                "Calibration transfers only to represented domains and missingness patterns; external evaluation remains required."
            ],
        )
