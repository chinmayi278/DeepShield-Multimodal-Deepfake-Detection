import reflex as rx

import unittest
from unittest.mock import MagicMock, patch
import numpy as np
from PIL import Image
from app.components.deepshield.adapters import MultilingualCheckpoint
from app.components.deepshield.audio import AudioService
from app.components.deepshield.config import Settings
from app.components.deepshield.contracts import Provenance, Result, TextRequest
from app.components.deepshield.image import ImageService
from app.components.deepshield.registry import ModelUnavailable, Registry
from app.components.deepshield.text import TextService


class OptionalLookupTests(unittest.TestCase):
    def test_optional_lookups_suppress_only_expected_absence(self):
        registry = Registry(Settings())
        for method, lookup, argument in (
            ("baseline", registry.available_baseline, "image"),
            ("adapter", registry.available_adapter, "reviewed:Adapter"),
        ):
            for error in (ModelUnavailable("missing"), FileNotFoundError()):
                with (
                    patch.object(registry, method, side_effect=error),
                    self.assertNoLogs(level="ERROR"),
                ):
                    self.assertIsNone(lookup(argument))
            loaded = MagicMock()
            with patch.object(registry, method, return_value=loaded):
                self.assertIs(lookup(argument), loaded)
            with patch.object(
                registry, method, side_effect=RuntimeError("unexpected")
            ):
                with self.assertRaises(RuntimeError):
                    lookup(argument)

    def test_image_absence_retains_quality_and_skips_inference(self):
        registry = Registry(Settings())
        service = ImageService(registry)
        with (
            patch.object(registry, "baseline", side_effect=ModelUnavailable()),
            patch.object(service, "score") as score,
            self.assertNoLogs(level="ERROR"),
        ):
            result = service.detect(Image.new("RGB", (64, 64)), explain=True)
        score.assert_not_called()
        self.assertEqual(
            result,
            Result(
                modality="image",
                reason="image_checkpoint_unavailable_or_incompatible",
                quality={
                    "width": 64.0,
                    "height": 64.0,
                    "contrast": 0.0,
                    "reliability": 0.0,
                },
            ),
        )

    def test_audio_absence_retains_signal_evidence(self):
        registry = Registry(Settings())
        waveform = np.full(16000, 0.1, dtype=np.float32)
        with (
            patch(
                "app.components.deepshield.audio.decode_audio",
                return_value=waveform,
            ),
            patch.object(registry, "baseline", side_effect=ModelUnavailable()),
            self.assertNoLogs(level="ERROR"),
        ):
            result = AudioService(registry).detect(b"decoded-by-test")
        self.assertEqual(result.status, "unavailable")
        self.assertEqual(
            result.reason, "audio_checkpoint_unavailable_or_incompatible"
        )
        self.assertIsNone(result.score)
        self.assertEqual(
            [item.kind for item in result.evidence], ["waveform", "log_mel"]
        )
        self.assertEqual(result.quality["duration_seconds"], 1.0)

    def test_missing_and_invalid_text_configuration_is_quiet(self):
        with (
            patch.dict("os.environ", {}, clear=True),
            self.assertNoLogs(level="ERROR"),
        ):
            with self.assertRaises(ModelUnavailable):
                MultilingualCheckpoint()
        with (
            patch.dict(
                "os.environ", {"DEEPSHIELD_TEXT_CONFIG": "reviewed.json"}
            ),
            patch("pathlib.Path.read_text", return_value="{}"),
            self.assertNoLogs(level="ERROR"),
        ):
            with self.assertRaises(ModelUnavailable):
                MultilingualCheckpoint()

    def test_text_lazy_absence_and_unexpected_failure(self):
        registry = Registry(Settings(text_adapter="reviewed:Adapter"))
        adapter = MagicMock()
        adapter.provenance = Provenance(language_scope=["en"])
        service = TextService(registry)
        request = TextRequest(
            text="This is a sample English passage for analysis.", language="en"
        )
        with patch.object(registry, "adapter", return_value=adapter):
            for error in (ModelUnavailable(), FileNotFoundError()):
                adapter.predict.side_effect = error
                with self.assertNoLogs(level="ERROR"):
                    result = service.detect(request)
                self.assertEqual(
                    result.reason, "text_checkpoint_unavailable_or_incompatible"
                )
                self.assertIsNone(result.score)
                self.assertEqual(
                    result.evidence[0].kind, "language_identification"
                )
            adapter.predict.side_effect = RuntimeError("unexpected")
            with patch("logging.exception") as log:
                result = service.detect(request)
            log.assert_called_once()
            self.assertEqual(result.status, "unavailable")
