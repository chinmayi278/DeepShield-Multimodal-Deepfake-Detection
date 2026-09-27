import reflex as rx

import unittest
from unittest.mock import AsyncMock, MagicMock
from app.components.review_support import clean, number, make_pdf, WARNING
from app.states.review_state import ReviewState
from app.components.deepshield.service import DetectionService
from app.components.deepshield.contracts import (
    DetectionResponse,
    Result,
    Provenance,
)
from app.models import ModalityResult


class ReviewGuards(unittest.TestCase):
    def test_missing_is_not_zero(self):
        self.assertIn("Unavailable", number(None))
        self.assertEqual(number(0), "0.000")
        self.assertEqual(number(0.72345), "0.723")

    def test_recursive_export_redactions(self):
        data = {
            "measurements": {
                "score": 0.7,
                "text": "private",
                "jpeg_base64": "private",
                "artifact_storage_key": "private",
                "box_xywh": [1, 2, 3, 4],
            },
            "owner_scope": "private",
        }
        redacted = clean(data)
        self.assertEqual(
            redacted, {"measurements": {"score": 0.7, "box_xywh": [1, 2, 3, 4]}}
        )

    def test_persistence_preserves_language_reliability_and_missing_score(self):
        response = DetectionResponse(
            request_id="review-test",
            results=[
                Result(
                    modality="text",
                    language="hi",
                    quality={"reliability": 0.4},
                    provenance=Provenance(),
                )
            ],
        )
        records = DetectionService.record_bundle(None, response, "test-scope")
        result = next(r for r in records if isinstance(r, ModalityResult))
        self.assertIsNone(result.indicators["score"])
        self.assertIsNone(result.fusion_weight)
        self.assertEqual(result.language_detected, "hi")
        self.assertEqual(result.reliability, 0.4)

    def test_pdf_is_real_document(self):
        payload = make_pdf(
            {
                "case": {"title": "Test case", "verdict": "Uncertain"},
                "warning": WARNING,
                "generated_at": "2026-01-01T00:00:00+00:00",
                "files": [],
                "results": [{"factuality": {"status": "not_assessed"}}],
                "evidence": [],
                "limits": "Raw media excluded",
            }
        )
        self.assertTrue(payload.startswith(b"%PDF-"))
        self.assertGreater(len(payload), 1000)


class AuthorizationGuards(unittest.IsolatedAsyncioTestCase):
    async def test_empty_scope_never_queries(self):
        session = AsyncMock()
        result = await ReviewState._fetch(
            None, session, "00000000-0000-0000-0000-000000000001", ""
        )
        self.assertIsNone(result)
        session.scalars.assert_not_called()

    async def test_authorization_precedes_children(self):
        session = AsyncMock()
        result = MagicMock()
        result.first.return_value = None
        session.scalars.return_value = result
        fetched = await ReviewState._fetch(
            None, session, "00000000-0000-0000-0000-000000000001", "scope-a"
        )
        self.assertIsNone(fetched)
        self.assertEqual(session.scalars.await_count, 1)
        query = session.scalars.call_args.args[0]
        sql = str(query)
        self.assertIn("owner_scope", sql)
        self.assertIn("deleted_at IS NULL", sql)
        self.assertIn("purged_at IS NULL", sql)
        self.assertIn("expires_at", sql)
        self.assertIn("scope-a", query.compile().params.values())
