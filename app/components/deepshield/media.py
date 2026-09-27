import reflex as rx

import base64
import io
import logging
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from app.components.deepshield.config import Settings


class InvalidMedia(ValueError):
    pass


def decode_base64(value: str, settings: Settings) -> bytes:
    try:
        data = base64.b64decode(value, validate=True)
    except Exception as e:
        logging.exception(f"Error: {e}")
        raise InvalidMedia("invalid_base64") from e
    if not data or len(data) > settings.max_media_bytes:
        raise InvalidMedia("empty_or_oversized_media")
    return data


def decode_image(data: bytes, settings: Settings):
    from PIL import Image, ImageOps

    try:
        with Image.open(io.BytesIO(data)) as source:
            if (
                source.width * source.height > settings.max_pixels
                or min(source.size) < 32
            ):
                raise InvalidMedia("unsupported_image_dimensions")
            source.load()
            return ImageOps.exif_transpose(source).convert("RGB")
    except Exception as e:
        logging.exception(f"Error: {e}")
        raise InvalidMedia("unreadable_image") from e


@contextmanager
def private_media(data: bytes):
    try:
        with tempfile.TemporaryDirectory(prefix="deepshield-") as directory:
            path = Path(directory) / "input.media"
            path.write_bytes(data)
            yield path
    except Exception as e:
        logging.exception(f"Error: {e}")
        raise


def decode_audio(data: bytes, settings: Settings):
    import numpy as np

    with private_media(data) as path:
        try:
            process = subprocess.run(
                [
                    "ffmpeg",
                    "-nostdin",
                    "-v",
                    "error",
                    "-protocol_whitelist",
                    "file,pipe",
                    "-i",
                    str(path),
                    "-t",
                    str(settings.max_duration + 1),
                    "-vn",
                    "-ac",
                    "1",
                    "-ar",
                    "16000",
                    "-f",
                    "f32le",
                    "pipe:1",
                ],
                capture_output=True,
                timeout=45,
                check=True,
            )
            waveform = np.frombuffer(process.stdout, dtype="<f4").copy()
        except FileNotFoundError as e:
            logging.exception("Unexpected error")
            raise RuntimeError("ffmpeg_unavailable") from e
        except (subprocess.CalledProcessError, ValueError) as e:
            logging.exception("Unexpected error")
            raise InvalidMedia("audio_decode_failed") from e
    if (
        waveform.size < 4000
        or waveform.size > settings.max_duration * 16000
        or not np.isfinite(waveform).all()
    ):
        raise InvalidMedia("audio_duration_or_samples_invalid")
    return waveform
