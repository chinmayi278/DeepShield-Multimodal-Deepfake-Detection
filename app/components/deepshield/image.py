import reflex as rx

import logging
from app.components.deepshield.contracts import Result, binary_verdict
from app.components.deepshield.explanation import faces, occlusion
from app.components.deepshield.registry import Registry


class ImageService:
    def __init__(self, registry: Registry):
        self.registry = registry

    def score(self, image) -> tuple[float, object]:
        import numpy as np
        from PIL import Image

        session, provenance = self.registry.baseline("image")
        scale = 440 / min(image.size)
        resized = image.resize(
            (int(image.width * scale), int(image.height * scale)),
            Image.Resampling.BICUBIC,
        )
        x, y = (resized.width - 384) // 2, (resized.height - 384) // 2
        pixels = (
            np.asarray(resized.crop((x, y, x + 384, y + 384)), dtype=np.float32)
            / 255
        )
        pixels = (
            pixels - np.array([0.4815, 0.4578, 0.4082], dtype=np.float32)
        ) / np.array([0.2686, 0.2613, 0.2758], dtype=np.float32)
        logits = np.asarray(
            session.run(
                None,
                {session.get_inputs()[0].name: pixels.transpose(2, 0, 1)[None]},
            )[0]
        )
        if logits.size != 1 or not np.isfinite(logits).all():
            raise ValueError("Single finite logit required")
        score = float(1 / (1 + np.exp(-np.clip(logits.item(), -80, 80))))
        return score, provenance

    def detect(
        self, image, explain: bool = False, face_evidence: bool = True
    ) -> Result:
        import numpy as np

        gray = np.asarray(
            image.resize((128, 128)).convert("L"), dtype=np.float32
        )
        quality = {
            "width": float(image.width),
            "height": float(image.height),
            "contrast": float(gray.std()),
            "reliability": min(1.0, min(image.size) / 384)
            * min(1.0, float(gray.std()) / 25),
        }
        result = Result(modality="image", quality=quality)
        try:
            if self.registry.available_baseline("image") is None:
                return Result(
                    modality="image",
                    quality=quality,
                    reason="image_checkpoint_unavailable_or_incompatible",
                )
            score, provenance = self.score(image)
            result = Result(
                modality="image",
                status="ok" if quality["reliability"] >= 0.5 else "degraded",
                score=score,
                score_semantics="uncalibrated_generated_image_score",
                provenance=provenance,
                quality=quality,
                verdict=binary_verdict(score),
                warnings=[
                    "Raw sigmoid score is an uncalibrated model score, not a probability of manipulation in the world.",
                    "Quality reliability is an operational gate, not a calibrated confidence.",
                    "Generated-image baseline is not a universal face-manipulation detector.",
                ],
            )
            if face_evidence:
                result.evidence.extend(faces(image))
            if explain:
                try:
                    result.evidence.append(
                        occlusion(
                            image, lambda value: self.score(value)[0], score
                        )
                    )
                except Exception as e:
                    logging.exception(
                        f"Unexpected image occlusion failure: {e}"
                    )
                    result.status = "degraded"
                    result.warnings.append("Occlusion explanation unavailable")
        except Exception as e:
            logging.exception(f"Unexpected image detection failure: {e}")
            result.reason = "image_checkpoint_unavailable_or_incompatible"
        return Result.model_validate(result.model_dump())
