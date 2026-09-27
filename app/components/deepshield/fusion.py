import reflex as rx

import logging
from app.components.deepshield.contracts import (
    Evidence,
    Provenance,
    Result,
    binary_verdict,
)
from app.components.deepshield.registry import Registry


class FusionService:
    def __init__(self, registry: Registry):
        self.registry = registry

    def detect(self, results: list[Result]) -> Result:
        settings = self.registry.settings
        by_modality = {r.modality: r for r in results}
        features = {}
        usable = []
        for modality in ("image", "video", "audio", "text"):
            item = by_modality.get(modality)
            available = bool(
                item
                and item.status in {"ok", "degraded"}
                and item.score is not None
            )
            quality = item.quality.get("reliability", 0.0) if item else 0.0
            calibrated = bool(
                item
                and item.provenance.calibrated
                and item.provenance.calibration_id
            )
            features[modality] = {
                "available": available,
                "missing": item is None,
                "quality": quality,
                "calibrated": calibrated,
                "score": item.score if available else None,
                "degraded": bool(item and item.status == "degraded"),
            }
            if available and calibrated and quality >= settings.quality_gate:
                usable.append(item)
        scores = [r.score for r in usable]
        disagreement = max(scores) - min(scores) if len(scores) > 1 else 0.0
        evidence = Evidence(
            kind="fusion_reliability_features",
            data={"modalities": features, "disagreement": disagreement},
        )
        if settings.fusion_adapter:
            try:
                result = Result.model_validate(
                    self.registry.adapter(settings.fusion_adapter)
                    .predict(evidence.data)
                    .model_dump()
                )
                if (
                    result.modality != "fusion"
                    or result.score is not None
                    and not result.provenance.calibrated
                ):
                    raise ValueError(
                        "Stacking output must include held-out calibration identity"
                    )
                result.evidence.append(evidence)
                if result.score is not None:
                    result.verdict = self._verdict(
                        result.score, disagreement, len(usable)
                    )
                return result
            except Exception as e:
                logging.exception(f"Error: {e}")
                return Result(
                    modality="fusion",
                    reason="stacking_adapter_unavailable",
                    evidence=[evidence],
                )
        preliminary = [
            item
            for modality in ("image", "video")
            for item in [by_modality.get(modality)]
            if item is not None
            and item.status in {"ok", "degraded"}
            and item.score is not None
            and not item.provenance.calibrated
        ]
        if not usable and preliminary:
            weights = [
                max(item.quality.get("reliability", 0.0), 0.01)
                for item in preliminary
            ]
            score = sum(
                weight * float(item.score)
                for weight, item in zip(weights, preliminary)
            ) / sum(weights)
            evidence.data["normalized_weights"] = {
                item.modality: weight / sum(weights)
                for item, weight in zip(preliminary, weights)
            }
            return Result(
                modality="fusion",
                status="degraded",
                score=score,
                verdict=binary_verdict(score),
                score_semantics="uncalibrated_reliability_weighted_image_video_evidence_aggregation",
                provenance=Provenance(
                    model_id="deepshield/reliability-gate",
                    revision="uncalibrated-1",
                ),
                quality={
                    "reliability": min(weights),
                    "modalities_used": float(len(preliminary)),
                },
                evidence=[evidence],
                warnings=[
                    "Preliminary model classification only; no calibrated probability or confidence is available.",
                    "Reliability-weighted raw detector scores are evidence aggregation, not a posterior probability.",
                    "Image and video-frame evidence may be correlated and must not be treated as independent confirmations.",
                ],
            )
        if not usable:
            return Result(
                modality="fusion",
                reason="no_reliable_calibrated_modalities",
                evidence=[evidence],
                warnings=[
                    "Raw detector scores are not averaged. Missing modalities are not neutral probabilities."
                ],
            )
        targets = {r.provenance.target for r in usable}
        calibration_ids = {r.provenance.calibration_id for r in usable}
        if len(targets) != 1 or len(calibration_ids) != 1:
            return Result(
                modality="fusion",
                reason="incompatible_calibration_domains",
                evidence=[evidence],
            )
        # Weighted evidence is not itself a calibrated posterior; abstain until a fitted stacker is supplied.
        weights = [
            r.quality["reliability"] * (0.5 if r.status == "degraded" else 1.0)
            for r in usable
        ]
        score = sum(
            weight * item.score for weight, item in zip(weights, usable)
        ) / sum(weights)
        evidence.data["normalized_weights"] = {
            item.modality: weight / sum(weights)
            for item, weight in zip(usable, weights)
        }
        return Result(
            modality="fusion",
            status="degraded",
            score=score,
            score_semantics="reliability_gated_calibrated_input_evidence_not_joint_probability",
            provenance=Provenance(
                model_id="deepshield/reliability-gate",
                revision="1",
                preprocessing="shared-calibration-domain-only",
                target=next(iter(targets)),
            ),
            quality={
                "reliability": min(weights),
                "disagreement": disagreement,
                "modalities_used": float(len(usable)),
            },
            evidence=[evidence],
            warnings=[
                "Joint fusion calibration is unavailable; verdict abstains.",
                "Image and video-frame evidence may be correlated; do not count them as independent confirmations.",
            ],
        )

    def _verdict(self, score: float, disagreement: float, usable: int) -> str:
        settings = self.registry.settings
        if (
            usable < 2
            or disagreement > settings.disagreement_gate
            or settings.abstain_low <= score <= settings.abstain_high
        ):
            return "uncertain"
        return "fake" if score > settings.abstain_high else "real"
