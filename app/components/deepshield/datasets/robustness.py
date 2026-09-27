import reflex as rx

import io
import logging
import subprocess
from pathlib import Path
from app.components.deepshield.contracts import Contract, Field
from app.components.deepshield.config import Settings
from app.components.deepshield.media import (
    decode_audio,
    decode_image,
    private_media,
)


class Augmentation(Contract):
    name: str = "none"
    severity: float = Field(default=0.2, ge=0, le=1)
    seed: int = 42
    background_audio: str = ""


class RobustnessTransform:
    def __init__(self, config: Augmentation):
        self.config = config

    def __call__(self, data: bytes, modality: str) -> bytes:
        import numpy as np
        from PIL import Image

        config = self.config
        if config.name == "none":
            return data
        rng = np.random.default_rng(config.seed)
        try:
            if modality == "image":
                image = decode_image(data, Settings())
                output = io.BytesIO()
                if config.name == "resize":
                    factor = 1 - 0.8 * config.severity
                    image = image.resize(
                        (
                            max(32, int(image.width * factor)),
                            max(32, int(image.height * factor)),
                        )
                    )
                elif config.name == "noise":
                    pixels = np.asarray(image, dtype=float)
                    image = Image.fromarray(
                        np.clip(
                            pixels
                            + rng.normal(0, config.severity * 30, pixels.shape),
                            0,
                            255,
                        ).astype("uint8")
                    )
                elif config.name != "compression":
                    raise ValueError(
                        "Unsupported image transform; background substitution requires a reviewed segmentation adapter"
                    )
                image.save(
                    output,
                    format="JPEG",
                    quality=max(5, int(95 - config.severity * 85))
                    if config.name == "compression"
                    else 95,
                )
                return output.getvalue()
            if modality == "audio" and config.name in {"noise", "background"}:
                import wave

                signal = decode_audio(data, Settings())
                if config.name == "noise":
                    interference = rng.normal(0, 1, len(signal))
                else:
                    if not config.background_audio:
                        raise ValueError(
                            "Background augmentation requires a real licensed audio file"
                        )
                    background = decode_audio(
                        Path(config.background_audio).read_bytes(), Settings()
                    )
                    interference = np.resize(background, len(signal))
                rms = np.sqrt(np.mean(signal**2))
                interference = interference / (
                    np.sqrt(np.mean(interference**2)) + 1e-8
                )
                signal = np.clip(
                    signal + interference * rms * config.severity, -1, 1
                )
                output = io.BytesIO()
                with wave.open(output, "wb") as stream:
                    stream.setnchannels(1)
                    stream.setsampwidth(2)
                    stream.setframerate(16000)
                    stream.writeframes((signal * 32767).astype("<i2").tobytes())
                return output.getvalue()
            if modality in {"video", "audio"} and config.name in {
                "codec",
                "compression",
                "video_quality",
                "resize",
            }:
                with private_media(data) as source:
                    destination = source.parent / (
                        "transformed.mp4"
                        if modality == "video"
                        else "transformed.mp3"
                    )
                    options = [
                        "-c:a",
                        "libmp3lame",
                        "-b:a",
                        f"{max(32, int(192 - 160 * config.severity))}k",
                    ]
                    if modality == "video":
                        options = [
                            "-an",
                            "-c:v",
                            "libx264",
                            "-preset",
                            "ultrafast",
                            "-crf",
                            str(int(18 + 30 * config.severity)),
                            "-pix_fmt",
                            "yuv420p",
                        ]
                        if config.name in {"resize", "video_quality"}:
                            options.extend(
                                ["-vf", "scale=trunc(iw/4)*2:trunc(ih/4)*2"]
                            )
                    subprocess.run(
                        [
                            "ffmpeg",
                            "-nostdin",
                            "-v",
                            "error",
                            "-protocol_whitelist",
                            "file,pipe",
                            "-i",
                            str(source),
                            "-t",
                            "120",
                            *options,
                            str(destination),
                        ],
                        check=True,
                        capture_output=True,
                        timeout=90,
                    )
                    return destination.read_bytes()
            raise ValueError(
                "Unsupported robustness transform for this modality"
            )
        except Exception as e:
            logging.exception(f"Error: {e}")
            raise
