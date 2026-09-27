import reflex as rx

import unittest
from pydantic import ValidationError
from app.components.deepshield.config import Settings
from app.components.deepshield.contracts import (
    DetectionResponse,
    Evidence,
    binary_verdict,
    MultimodalRequest,
    Result,
    TextRequest,
)
from app.components.deepshield.datasets.loaders import (
    Sample,
    connected_groups,
    split_manifest,
    validate_splits,
)
from app.components.deepshield.fusion import FusionService
from app.components.deepshield.registry import Registry
from app.components.deepshield.service import DetectionService


class ContractTests(unittest.TestCase):
    def test_failure_has_no_score(self):
        with self.assertRaises(ValidationError):
            Result(
                modality="image",
                status="unavailable",
                score=0.5,
                score_semantics="uncalibrated",
            )

    def test_nonfinite_score_rejected(self):
        with self.assertRaises(ValidationError):
            Result(
                modality="text",
                status="ok",
                score=float("nan"),
                score_semantics="uncalibrated",
            )

    def test_reversed_interval_rejected(self):
        with self.assertRaises(ValidationError):
            Evidence(kind="segment", start_ms=100, end_ms=50)

    def test_empty_multimodal_rejected(self):
        with self.assertRaises(ValidationError):
            MultimodalRequest()

    def test_no_heuristic_text_probability(self):
        result = DetectionService(Settings()).detect(
            "text",
            TextRequest(
                text="This is a sufficiently long original text for a language identification check."
            ),
        )
        self.assertEqual(result.status, "unavailable")
        self.assertIsNone(result.score)
        self.assertEqual(result.factuality, "not_assessed")

    def test_single_uncalibrated_detector_preliminary_fusion(self):
        result = FusionService(Registry(Settings())).detect(
            [
                Result(
                    modality="image",
                    status="ok",
                    score=0.7,
                    verdict="fake",
                    score_semantics="test_fixture_not_prediction",
                )
            ]
        )
        self.assertEqual(result.verdict, "fake")
        self.assertEqual(result.status, "degraded")
        self.assertEqual(result.provenance.calibration_id, "")
        self.assertTrue(
            result.evidence[0].data["modalities"]["audio"]["missing"]
        )

    def test_binary_threshold_and_uncalibrated_contract(self):
        self.assertEqual(binary_verdict(0.51), "fake")
        self.assertEqual(binary_verdict(0.49), "real")
        for verdict, score in (("fake", 0.51), ("real", 0.49)):
            result = Result(
                modality="image",
                status="ok",
                score=score,
                verdict=verdict,
                score_semantics="unit_test_fixture",
            )
            self.assertIn(result.verdict, {"real", "fake"})
            self.assertIsNotNone(result.score)
        unavailable = Result(modality="image")
        self.assertEqual(unavailable.verdict, "uncertain")
        self.assertIsNone(unavailable.score)

    def test_record_bundle_persists_verdict_without_raw_probability(self):
        response = DetectionResponse(
            request_id="contract-test",
            results=[
                Result(
                    modality="image",
                    status="ok",
                    score=0.7,
                    score_semantics="unit_test_fixture",
                )
            ],
        )
        records = DetectionService(Settings()).record_bundle(
            response, "unit-test-owner"
        )
        self.assertIsNone(records[1].fake_probability)
        self.assertIsNotNone(records[0].expires_at)

    def test_connected_identity_leakage(self):
        rows = [
            Sample(
                id="a",
                path="a",
                modality="video",
                label=0,
                dataset="test",
                group="g1",
                subject="subject",
                sha256="a",
                split="train",
            ),
            Sample(
                id="b",
                path="b",
                modality="video",
                label=0,
                dataset="test",
                group="g2",
                subject="subject",
                sha256="b",
                split="test",
            ),
        ]
        self.assertEqual(len(set(connected_groups(rows))), 1)
        with self.assertRaises(ValueError):
            validate_splits(rows)

    def test_repeatable_group_split(self):
        rows = [
            Sample(
                id=str(i),
                path=str(i),
                modality="image",
                label=i % 2,
                dataset="unit-test",
                group=str(i // 2),
                sha256=str(i),
            )
            for i in range(60)
        ]
        first = split_manifest(rows, 42)
        second = split_manifest([s.model_copy() for s in rows], 42)
        self.assertEqual([s.split for s in first], [s.split for s in second])
        validate_splits(first)


if __name__ == "__main__":
    unittest.main()
