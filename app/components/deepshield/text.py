import reflex as rx

import contextlib
import logging
from app.components.deepshield.contracts import Evidence, Result, TextRequest
from app.components.deepshield.language import LanguageService
from app.components.deepshield.registry import ModelUnavailable, Registry


class TextService:
    def __init__(self, registry: Registry):
        self.registry = registry
        self.language = LanguageService()

    def detect(self, request: TextRequest) -> Result:
        text = request.text
        if not text.strip() or any(0xD800 <= ord(c) <= 0xDFFF for c in text):
            return Result(
                modality="text",
                status="invalid_input",
                reason="empty_or_invalid_unicode",
            )
        language = self.language.detect(text, request.language)
        evidence = [
            Evidence(
                kind="language_identification",
                data=language.model_dump(mode="json"),
            )
        ]
        quality = {
            "characters": float(len(text)),
            "reliability": min(1.0, len(text.strip()) / 500),
        }
        if not self.registry.settings.text_adapter:
            return Result(
                modality="text",
                reason="no_validated_multilingual_detector_configured",
                language=language.language,
                quality=quality,
                evidence=evidence,
                warnings=language.warnings,
            )
        unavailable = Result(
            modality="text",
            reason="text_checkpoint_unavailable_or_incompatible",
            language=language.language,
            evidence=evidence,
            quality=quality,
        )
        try:
            adapter = self.registry.available_adapter(
                self.registry.settings.text_adapter
            )
            if adapter is None:
                return unavailable
            if language.language not in adapter.provenance.language_scope:
                return Result(
                    modality="text",
                    reason="unsupported_or_uncertain_language",
                    language=language.language,
                    evidence=evidence,
                    quality=quality,
                )
            result = None
            with contextlib.suppress(ModelUnavailable, FileNotFoundError):
                result = Result.model_validate(
                    adapter.predict(
                        {"text": text, "language": language.language}
                    ).model_dump()
                )
            if result is None or result.modality != "text":
                return unavailable
            for item in result.evidence:
                if item.kind in {"text_span", "text_chunk"}:
                    start, end = (
                        item.data.get("start_char"),
                        item.data.get("end_char"),
                    )
                    if (
                        not isinstance(start, int)
                        or not isinstance(end, int)
                        or not 0 <= start < end <= len(text)
                    ):
                        raise ValueError(
                            "Invalid original-Unicode character offsets"
                        )
            result.language = language.language
            result.evidence.extend(evidence)
            result.warnings.extend(language.warnings)
            return result
        except Exception as e:
            logging.exception(f"Unexpected text detection failure: {e}")
            return Result(
                modality="text",
                reason="text_checkpoint_unavailable_or_incompatible",
                language=language.language,
                evidence=evidence,
                quality=quality,
            )
