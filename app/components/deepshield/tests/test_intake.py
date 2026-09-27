import reflex as rx

import io
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from PIL import Image
from app.states.intake_state import IntakeState, inspect_file
from app.components.deepshield.contracts import DetectionResponse, Result
from app.components.deepshield.service import DetectionService
from app.models import ModalityResult


class IntakeValidationTests(unittest.TestCase):
    def test_safe_image_preview_and_hash(self):
        buffer = io.BytesIO()
        Image.new("RGB", (64, 64)).save(buffer, format="PNG")
        first = inspect_file(buffer.getvalue(), "test.png")
        second = inspect_file(buffer.getvalue(), "copy.png")
        self.assertEqual(first["hash"], second["hash"])
        self.assertEqual(first["modality"], "image")
        self.assertTrue(first["preview"].startswith("data:image/jpeg;base64,"))
        self.assertEqual(first["width"], "64")

    def test_spoofed_audio_rejected(self):
        with self.assertRaises(ValueError):
            inspect_file(b"not an audio file", "recording.wav")

    def test_active_content_rejected(self):
        with self.assertRaises(ValueError):
            inspect_file(b"<svg/>", "image.svg")

    def test_unsupported_extensions_list_only_supported_formats(self):
        buffer = io.BytesIO()
        Image.new("RGB", (64, 64)).save(buffer, format="PNG")
        for name in (
            "evidence.exe",
            "image.svg",
            "image.gif",
            "clip.avi",
            "audio.ogg",
            "unnamed",
        ):
            with (
                self.subTest(name=name),
                self.assertRaises(ValueError) as caught,
            ):
                inspect_file(buffer.getvalue(), name)
            self.assertEqual(
                str(caught.exception),
                "Unsupported extension. Accepted formats: JPG/JPEG/PNG/WebP, MP4/WebM/MOV, WAV/MP3/FLAC/M4A.",
            )

    def test_spoofed_media_signatures_rejected(self):
        for suffix in ("wav", "mp3", "flac", "m4a", "mp4", "webm", "mov"):
            with (
                self.subTest(suffix=suffix),
                self.assertRaisesRegex(
                    ValueError, "The file content does not match its extension"
                ),
            ):
                inspect_file(b"not supported media", f"evidence.{suffix}")

    def test_empty_rejected(self):
        with self.assertRaises(ValueError):
            inspect_file(b"", "image.png")

    def test_unavailable_has_no_persisted_score(self):
        response = DetectionResponse(
            request_id="test",
            results=[Result(modality="text", reason="checkpoint_unavailable")],
        )
        records = DetectionService().record_bundle(response, "test-owner")
        result = next(
            record for record in records if isinstance(record, ModalityResult)
        )
        self.assertEqual(str(result.status), "unavailable")
        self.assertIsNone(result.fake_probability)
        self.assertIsNone(result.indicators["score"])
        self.assertEqual(result.factuality_assessment["status"], "not_assessed")


class UploadErrorTests(unittest.IsolatedAsyncioTestCase):
    async def test_validation_errors_are_visible_without_error_logs(self):
        for name, data, mode, message in (
            (
                "evidence.exe",
                b"not-supported",
                "image",
                "Unsupported extension. Accepted formats: JPG/JPEG/PNG/WebP, MP4/WebM/MOV, WAV/MP3/FLAC/M4A.",
            ),
            (
                "evidence.wav",
                b"not audio",
                "audio",
                "The file content does not match its extension.",
            ),
            (
                "evidence.png",
                b"",
                "image",
                "Empty file or size exceeds the image limit.",
            ),
        ):
            with self.subTest(name=name):
                state = SimpleNamespace(
                    busy=False,
                    uploading=False,
                    progress=12,
                    error="old error",
                    mode=mode,
                    files=[],
                    _payloads={},
                )
                upload = SimpleNamespace(
                    name=name,
                    content_type="image/png",
                    read=AsyncMock(return_value=data),
                    close=AsyncMock(),
                )
                with (
                    self.assertNoLogs(level="ERROR"),
                    patch("app.states.intake_state.logging.exception") as log,
                ):
                    await IntakeState.upload.fn(state, [upload])
                log.assert_not_called()
                self.assertEqual(state.error, message)
                self.assertFalse(state.uploading)
                self.assertEqual(state.progress, 100)
                self.assertEqual(state.files, [])
                self.assertEqual(state._payloads, {})
                upload.close.assert_awaited_once()

    async def test_unexpected_failure_logs_and_closes_even_unread_uploads(self):
        state = SimpleNamespace(
            busy=False,
            uploading=False,
            progress=12,
            error="",
            mode="multimodal",
            files=[],
            _payloads={},
        )
        uploads = [
            SimpleNamespace(
                name="evidence.png",
                read=AsyncMock(side_effect=OSError("read failed")),
                close=AsyncMock(),
            ),
            SimpleNamespace(
                name="evidence.wav", read=AsyncMock(), close=AsyncMock()
            ),
        ]
        with self.assertLogs(level="ERROR") as logs:
            await IntakeState.upload.fn(state, uploads)
        self.assertEqual(
            state.error, "Unable to read this file. Try a different file."
        )
        self.assertEqual(len(logs.records), 1)
        self.assertEqual(logs.records[0].getMessage(), "Error: read failed")
        self.assertIsNotNone(logs.records[0].exc_info)
        self.assertFalse(state.uploading)
        self.assertEqual(state.progress, 100)
        for upload in uploads:
            upload.close.assert_awaited_once()
        uploads[1].read.assert_not_awaited()

    async def test_count_validation_closes_every_upload_without_logging(self):
        state = SimpleNamespace(
            busy=False,
            uploading=False,
            progress=12,
            error="",
            mode="image",
            files=[],
            _payloads={},
        )
        uploads = [
            SimpleNamespace(read=AsyncMock(), close=AsyncMock())
            for _ in range(2)
        ]
        with (
            self.assertNoLogs(level="ERROR"),
            patch("app.states.intake_state.logging.exception") as log,
        ):
            await IntakeState.upload.fn(state, uploads)
        log.assert_not_called()
        self.assertEqual(
            state.error,
            "Select one file per modality; multimodal accepts up to three media files.",
        )
        self.assertFalse(state.uploading)
        self.assertEqual(state.progress, 100)
        for upload in uploads:
            upload.read.assert_not_awaited()
            upload.close.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
