import reflex as rx

import os
from pydantic import Field
from app.components.deepshield.contracts import Contract


class Settings(Contract):
    max_media_bytes: int = Field(default=32 * 1024 * 1024, ge=1024)
    max_body_bytes: int = 45 * 1024 * 1024
    max_pixels: int = 16000000
    max_duration: float = 120.0
    max_frames: int = 12
    max_audio_windows: int = 40
    download_budget: int = 300 * 1024 * 1024
    allow_downloads: bool = True
    image_revision: str = "ac6ee457bea9"
    audio_revision: str = "ee0187142973"
    image_local: str = ""
    audio_local: str = ""
    image_sha256: str = ""
    audio_sha256: str = ""
    text_adapter: str = ""
    temporal_adapter: str = ""
    fusion_adapter: str = ""
    quality_gate: float = Field(default=0.5, ge=0, le=1)
    abstain_low: float = Field(default=0.35, ge=0, le=1)
    abstain_high: float = Field(default=0.65, ge=0, le=1)
    disagreement_gate: float = Field(default=0.4, ge=0, le=1)

    @classmethod
    def from_environment(cls):
        return cls(
            allow_downloads=os.environ.get("DEEPSHIELD_DOWNLOADS", "1") != "0",
            image_local=os.environ.get("DEEPSHIELD_IMAGE_LOCAL", ""),
            audio_local=os.environ.get("DEEPSHIELD_AUDIO_LOCAL", ""),
            image_sha256=os.environ.get("DEEPSHIELD_IMAGE_SHA256", ""),
            audio_sha256=os.environ.get("DEEPSHIELD_AUDIO_SHA256", ""),
            text_adapter=os.environ.get("DEEPSHIELD_TEXT_ADAPTER", ""),
            temporal_adapter=os.environ.get("DEEPSHIELD_TEMPORAL_ADAPTER", ""),
            fusion_adapter=os.environ.get("DEEPSHIELD_FUSION_ADAPTER", ""),
        )
