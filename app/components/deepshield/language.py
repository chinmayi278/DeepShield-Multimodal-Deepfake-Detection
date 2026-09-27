import reflex as rx

import logging
import threading
from app.components.deepshield.contracts import Contract, Field


class LanguageResult(Contract):
    language: str = "und"
    confidence: float | None = Field(default=None, ge=0, le=1)
    method: str = "undetermined"
    warnings: list[str] = Field(default_factory=list)


class LanguageService:
    def __init__(self):
        self._lock = threading.Lock()

    def detect(self, text: str, requested: str = "auto") -> LanguageResult:
        if requested not in {"auto", "und"}:
            return LanguageResult(
                language=requested,
                method="user_selected",
                warnings=["Manual language selection is not verified."],
            )
        if len(text.strip()) < 20:
            return LanguageResult(
                warnings=[
                    "Too little text for reliable language identification."
                ]
            )
        try:
            from langdetect import DetectorFactory, detect_langs

            with self._lock:
                DetectorFactory.seed = 42
                detected = detect_langs(text[:10000])
            top = detected[0]
            supported = {"en", "hi", "kn", "ta", "te", "ml", "mr", "bn"}
            return LanguageResult(
                language=top.lang
                if top.lang in supported and top.prob >= 0.8
                else "und",
                confidence=float(top.prob),
                method="langdetect_original_unicode",
                warnings=[
                    "Language identification confidence is not detector confidence; mixed-language text may be ambiguous."
                ],
            )
        except Exception as e:
            logging.exception(f"Error: {e}")
            return LanguageResult(
                warnings=["Language identification unavailable."]
            )
