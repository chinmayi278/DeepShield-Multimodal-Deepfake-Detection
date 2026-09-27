import reflex as rx

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

Modality = Literal["image", "video", "audio", "text", "fusion"]
Language = Literal[
    "auto", "en", "hi", "kn", "ta", "te", "ml", "mr", "bn", "und"
]


def binary_verdict(score: float) -> Literal["real", "fake"]:
    return "fake" if score > 0.5 else "real"


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Provenance(Contract):
    model_id: str = ""
    revision: str = ""
    artifact_sha256: str = ""
    preprocessing: str = ""
    runtime: str = ""
    license: str = ""
    calibrated: bool = False
    calibration_id: str = ""
    target: str = "synthetic_origin"
    language_scope: list[str] = Field(default_factory=list)


class Evidence(Contract):
    kind: str
    start_ms: int | None = Field(default=None, ge=0)
    end_ms: int | None = Field(default=None, ge=0)
    score: float | None = Field(default=None, ge=0, le=1)
    data: dict[str, JsonValue] = Field(default_factory=dict)
    scope: str = "model_behavior_not_proof"

    @model_validator(mode="after")
    def ordered(self):
        if (
            self.start_ms is not None
            and self.end_ms is not None
            and self.end_ms < self.start_ms
        ):
            raise ValueError("Reversed evidence interval")
        return self


class Result(Contract):
    modality: Modality
    status: Literal["ok", "unavailable", "degraded", "invalid_input"] = (
        "unavailable"
    )
    score: float | None = Field(default=None, ge=0, le=1)
    score_semantics: str = "not_assessed"
    verdict: Literal["real", "fake", "uncertain"] = "uncertain"
    reason: str = ""
    provenance: Provenance = Field(default_factory=Provenance)
    quality: dict[str, float] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    language: str = "und"
    factuality: Literal["not_assessed"] = "not_assessed"
    limitations: list[str] = Field(
        default_factory=lambda: [
            "Detector evidence is not proof of manipulation, authorship, identity, or factuality.",
            "Do not use as sole evidence for high-stakes decisions.",
        ]
    )

    @model_validator(mode="after")
    def score_contract(self):
        if (
            self.status in {"unavailable", "invalid_input"}
            and self.score is not None
        ):
            raise ValueError("Failed pipelines cannot carry scores")
        if self.provenance.calibrated and not self.provenance.calibration_id:
            raise ValueError(
                "Calibration requires a validation artifact identity"
            )
        if self.score is not None and self.score_semantics == "not_assessed":
            raise ValueError("Score semantics required")
        if (
            not self.provenance.calibrated
            and self.verdict != "uncertain"
            and (
                self.status not in {"ok", "degraded"}
                or self.score is None
                or self.score_semantics == "not_assessed"
            )
        ):
            raise ValueError(
                "Uncalibrated classifications require a successful finite score and explicit semantics"
            )
        return self


class MediaRequest(Contract):
    data_base64: str = Field(min_length=4, max_length=44000000)
    language: Language = "auto"
    explain: bool = False


class TextRequest(Contract):
    text: str = Field(min_length=1, max_length=20000)
    language: Language = "auto"


class MultimodalRequest(Contract):
    image: MediaRequest | None = None
    video: MediaRequest | None = None
    audio: MediaRequest | None = None
    text: TextRequest | None = None

    @model_validator(mode="after")
    def nonempty(self):
        if not any((self.image, self.video, self.audio, self.text)):
            raise ValueError("At least one modality is required")
        return self


class DetectionResponse(Contract):
    request_id: str
    results: list[Result]
    fusion: Result | None = None
    persisted: bool = False
