import reflex as rx

import hashlib
import logging
import threading
import time
from uuid import uuid4
from app.components.deepshield.audio import AudioService
from app.components.deepshield.config import Settings
from app.components.deepshield.contracts import (
    DetectionResponse,
    MediaRequest,
    MultimodalRequest,
    Result,
    TextRequest,
)
from app.components.deepshield.fusion import FusionService
from app.components.deepshield.image import ImageService
from app.components.deepshield.media import (
    InvalidMedia,
    decode_base64,
    decode_image,
)
from app.components.deepshield.registry import Registry
from app.components.deepshield.text import TextService
from app.components.deepshield.video import VideoService


class DetectionService:
    """Synchronous bounded worker boundary; call with asyncio.to_thread from Reflex events."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings.from_environment()
        self.registry = Registry(self.settings)
        self._gate = threading.Lock()
        self.image = ImageService(self.registry)
        self.video = VideoService(self.registry)
        self.audio = AudioService(self.registry)
        self.text = TextService(self.registry)
        self.fusion = FusionService(self.registry)

    def detect(
        self, modality: str, request: MediaRequest | TextRequest
    ) -> Result:
        started = time.monotonic()
        with self._gate:
            try:
                if modality == "text":
                    result = self.text.detect(
                        TextRequest.model_validate(request.model_dump())
                    )
                else:
                    data = decode_base64(request.data_base64, self.settings)
                    if modality == "image":
                        result = self.image.detect(
                            decode_image(data, self.settings), request.explain
                        )
                    elif modality == "video":
                        result = self.video.detect(data, request.explain)
                    elif modality == "audio":
                        result = self.audio.detect(data, request.language)
                    else:
                        raise ValueError("Unsupported modality")
                result = Result.model_validate(result.model_dump())
            except InvalidMedia as e:
                logging.exception(f"Error: {e}")
                result = Result(
                    modality=modality,
                    status="invalid_input",
                    reason="media_validation_failed",
                )
            except Exception as e:
                logging.exception(f"Error: {e}")
                result = Result(
                    modality=modality, reason="pipeline_unavailable"
                )
        logging.info(
            '{"event":"detection","modality":"%s","status":"%s","elapsed_ms":%.0f}',
            modality,
            result.status,
            (time.monotonic() - started) * 1000,
        )
        return result

    def multimodal(self, request: MultimodalRequest) -> DetectionResponse:
        results = []
        for modality in ("image", "video", "audio", "text"):
            value = getattr(request, modality)
            if value is not None:
                results.append(self.detect(modality, value))
        return DetectionResponse(
            request_id=str(uuid4()),
            results=results,
            fusion=self.fusion.detect(results),
        )

    def record_bundle(self, response: DetectionResponse, owner_scope: str):
        """Build existing ORM records for the authorized persistence owner; performs no database writes."""
        from datetime import datetime, timedelta, timezone
        from app.models import (
            Analysis,
            EvidenceRecord,
            Modality,
            ModalityResult,
            ProcessingStatus,
            Verdict,
        )

        now = datetime.now(timezone.utc)
        analysis = Analysis(
            id=uuid4(),
            owner_scope=owner_scope,
            correlation_id=response.request_id,
            pipeline_version="0.2.0",
            status=ProcessingStatus.COMPLETED,
            started_at=now,
            finished_at=now,
            verdict=Verdict.UNCERTAIN,
            retention_policy="ephemeral-review-24h",
            expires_at=now + timedelta(days=1),
        )
        records = [analysis]
        outputs = list(response.results)
        if response.fusion:
            outputs.append(response.fusion)
        fusion_weights = {}
        if response.fusion:
            for item in response.fusion.evidence:
                fusion_weights.update(item.data.get("normalized_weights", {}))
        for result in outputs:
            status = {
                "ok": ProcessingStatus.COMPLETED,
                "degraded": ProcessingStatus.DEGRADED,
                "unavailable": ProcessingStatus.UNAVAILABLE,
                "invalid_input": ProcessingStatus.FAILED,
            }[result.status]
            record = ModalityResult(
                id=uuid4(),
                analysis_id=analysis.id,
                modality=Modality(result.modality),
                status=status,
                started_at=now,
                finished_at=now,
                failure_code=result.reason or None,
                verdict=Verdict(result.verdict),
                fake_probability=result.score
                if result.provenance.calibrated
                else None,
                quality_metrics=result.quality,
                reliability=result.quality.get("reliability"),
                fusion_weight=fusion_weights.get(result.modality),
                included_in_fusion=result.modality in fusion_weights,
                language_detected=result.language,
                calibration_version=result.provenance.calibration_id or None,
                indicators={
                    "score": result.score,
                    "semantics": result.score_semantics,
                },
                model_provenance_snapshot=result.provenance.model_dump(
                    mode="json"
                ),
                factuality_assessment={"status": "not_assessed"},
                limitations={
                    "warnings": result.warnings,
                    "limitations": result.limitations,
                },
                retention_policy=analysis.retention_policy,
                expires_at=analysis.expires_at,
            )
            records.append(record)
            for index, evidence in enumerate(result.evidence):
                # Crops and excerpts are deliberately omitted from persistence metadata.
                data = {
                    key: value
                    for key, value in evidence.data.items()
                    if key not in {"jpeg_base64", "text", "spatial_evidence"}
                }
                records.append(
                    EvidenceRecord(
                        modality_result_id=record.id,
                        kind=evidence.kind,
                        sequence_number=index,
                        start_ms=evidence.start_ms,
                        end_ms=evidence.end_ms,
                        measurements=data,
                        explanation={
                            "scope": evidence.scope,
                            "score": evidence.score,
                        },
                        retention_policy=analysis.retention_policy,
                        expires_at=analysis.expires_at,
                    )
                )
        return records
