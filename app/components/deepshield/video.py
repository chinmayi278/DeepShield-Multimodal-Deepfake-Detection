import reflex as rx

import contextlib
import logging
from app.components.deepshield.contracts import Evidence, Result, binary_verdict
from app.components.deepshield.image import ImageService
from app.components.deepshield.media import InvalidMedia, private_media
from app.components.deepshield.registry import ModelUnavailable, Registry


class VideoService:
    def __init__(self, registry: Registry):
        self.registry = registry
        self.image = ImageService(registry)

    def detect(self, data: bytes, explain: bool = False) -> Result:
        import cv2
        import numpy as np
        from PIL import Image

        settings = self.registry.settings
        evidence = []
        scores = []
        changes = []
        qualities = []
        provenance = None
        with private_media(data) as path:
            capture = cv2.VideoCapture(str(path))
            try:
                fps = capture.get(cv2.CAP_PROP_FPS)
                count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
                width, height = (
                    capture.get(cv2.CAP_PROP_FRAME_WIDTH),
                    capture.get(cv2.CAP_PROP_FRAME_HEIGHT),
                )
                if (
                    not capture.isOpened()
                    or not np.isfinite(fps)
                    or fps <= 0
                    or count < 2
                ):
                    raise InvalidMedia("invalid_video_metadata")
                if (
                    count / fps > settings.max_duration
                    or width * height > settings.max_pixels
                ):
                    raise InvalidMedia("video_limits_exceeded")
                candidates = np.unique(
                    np.linspace(
                        0, count - 1, min(settings.max_frames * 3, count)
                    ).astype(int)
                )
                thumbnails = []
                previous = None
                for frame_index in candidates:
                    capture.set(cv2.CAP_PROP_POS_FRAMES, int(frame_index))
                    ok, frame = capture.read()
                    if not ok:
                        continue
                    thumbnail = cv2.resize(
                        cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (64, 64)
                    )
                    change = (
                        float(
                            np.mean(np.abs(thumbnail.astype(float) - previous))
                        )
                        / 255
                        if previous is not None
                        else 0.0
                    )
                    thumbnails.append((int(frame_index), change))
                    previous = thumbnail.astype(float)
                if not thumbnails:
                    raise InvalidMedia("no_decodable_video_frames")
                anchors = {
                    thumbnails[i][0]
                    for i in np.linspace(
                        0,
                        len(thumbnails) - 1,
                        min(len(thumbnails), max(2, settings.max_frames // 2)),
                    ).astype(int)
                }
                for index, change in sorted(
                    thumbnails, key=lambda item: item[1], reverse=True
                ):
                    if len(anchors) >= settings.max_frames:
                        break
                    anchors.add(index)
                for index in sorted(anchors):
                    capture.set(cv2.CAP_PROP_POS_FRAMES, index)
                    ok, frame = capture.read()
                    if not ok:
                        continue
                    result = self.image.detect(
                        Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)),
                        explain=explain,
                    )
                    timestamp = int(index / fps * 1000)
                    evidence.append(
                        Evidence(
                            kind="frame",
                            start_ms=timestamp,
                            score=result.score,
                            data={
                                "frame_index": index,
                                "status": result.status,
                                "quality": result.quality,
                                "spatial_evidence": [
                                    e.model_dump(mode="json")
                                    for e in result.evidence
                                ],
                            },
                        )
                    )
                    if result.score is not None:
                        scores.append(result.score)
                        qualities.append(result.quality.get("reliability", 0))
                        provenance = result.provenance
                changes = [change for _, change in thumbnails]
            finally:
                capture.release()
        if not scores:
            return Result(
                modality="video",
                reason="no_available_frame_detector",
                evidence=evidence,
                quality={"decoded_candidates": float(len(thumbnails))},
            )
        evidence.append(
            Evidence(
                kind="temporal_diagnostics",
                data={
                    "mean_visual_change": float(np.mean(changes)),
                    "frame_score_std": float(np.std(scores)),
                    "adjacent_score_delta": float(
                        np.mean(np.abs(np.diff(scores)))
                    )
                    if len(scores) > 1
                    else 0.0,
                    "q90_frame_score": float(np.quantile(scores, 0.9)),
                    "sampling": "uniform_anchors_plus_scene_change",
                    "highest_score_timestamps_ms": [
                        e.start_ms
                        for e in sorted(
                            evidence,
                            key=lambda e: (
                                e.score if e.score is not None else -1
                            ),
                            reverse=True,
                        )[:3]
                    ],
                    "scope": "descriptive_consistency_not_trained_temporal_detection",
                },
            )
        )
        result = Result(
            modality="video",
            status="degraded",
            score=float(np.median(scores)),
            verdict=binary_verdict(float(np.median(scores))),
            score_semantics="median_sampled_frame_generated_image_score_uncalibrated",
            provenance=provenance,
            evidence=evidence,
            quality={
                "reliability": float(np.mean(qualities)),
                "frames_scored": float(len(scores)),
                "sampling_coverage": len(scores) / count,
            },
            warnings=[
                "Preliminary model classification from sampled frames; not temporal proof and not a calibrated probability.",
                "Audio track not assessed.",
                "Highest scoring timestamps are rankings, not validated suspicious-event thresholds.",
            ],
        )
        if settings.temporal_adapter:
            try:
                adapter = self.registry.available_adapter(
                    settings.temporal_adapter
                )
                temporal = None
                if adapter is not None:
                    with contextlib.suppress(
                        ModelUnavailable, FileNotFoundError
                    ):
                        temporal = Result.model_validate(
                            adapter.predict(
                                {"media": data, "frame_result": result}
                            ).model_dump()
                        )
                if temporal is None or temporal.modality != "video":
                    result.warnings.append(
                        "Configured temporal checkpoint unavailable; returning frame evidence only."
                    )
                    return result
                temporal.evidence.extend(result.evidence)
                temporal.warnings.append(
                    "Frame diagnostics remain distinct from trained temporal output."
                )
                return temporal
            except Exception as e:
                logging.exception(f"Unexpected temporal detection failure: {e}")
                result.warnings.append(
                    "Configured temporal checkpoint unavailable; returning frame evidence only."
                )
        return result
