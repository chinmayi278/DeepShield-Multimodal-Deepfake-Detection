import reflex as rx

import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from PIL import Image
from app.components.deepshield.config import Settings
from app.components.deepshield.registry import ModelUnavailable, Registry
from app.components.deepshield.image import ImageService
from app.states.review_state import ReviewState


class DetectorAvailabilityTests(unittest.TestCase):
    def test_expected_loading_failure_is_quiet_and_scoreless(self):
        registry = Registry(Settings())
        with (
            patch.object(
                registry, "_load", side_effect=ModelUnavailable("disabled")
            ),
            patch("logging.exception") as log,
        ):
            result = ImageService(registry).detect(Image.new("RGB", (64, 64)))
        self.assertEqual(result.status, "unavailable")
        self.assertIsNone(result.score)
        log.assert_not_called()

    def test_unexpected_loading_failure_logged_once(self):
        registry = Registry(Settings())
        with (
            patch.object(
                registry, "_load", side_effect=RuntimeError("integrity failure")
            ),
            patch("logging.exception") as log,
        ):
            result = ImageService(registry).detect(Image.new("RGB", (64, 64)))
        self.assertIsNone(result.score)
        log.assert_called_once()

    def test_missing_checkpoint_is_quiet(self):
        registry = Registry(Settings())
        with (
            patch.object(registry, "_load", side_effect=FileNotFoundError()),
            patch("logging.exception") as log,
        ):
            with self.assertRaises(ModelUnavailable):
                registry.baseline("audio")
        log.assert_not_called()


class ExpectedAuthorizationTests(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_identifiers_do_not_query(self):
        for identifier, owner in [
            ("", "scope"),
            ("invalid", "scope"),
            ("00000000-0000-0000-0000-000000000001", ""),
        ]:
            session = AsyncMock()
            result = await ReviewState._fetch(None, session, identifier, owner)
            self.assertIsNone(result)
            session.scalars.assert_not_called()

    async def test_unavailable_record_uses_scoped_query(self):
        session = AsyncMock()
        rows = MagicMock()
        rows.first.return_value = None
        session.scalars.return_value = rows
        result = await ReviewState._fetch(
            None, session, "00000000-0000-0000-0000-000000000001", "scope"
        )
        self.assertIsNone(result)
        query = session.scalars.call_args.args[0]
        self.assertIn("owner_scope", str(query))
        self.assertIn("expires_at", str(query))
        self.assertEqual(session.scalars.await_count, 1)

    async def test_database_failure_remains_unexpected(self):
        session = AsyncMock()
        session.scalars.side_effect = RuntimeError("database failure")
        with self.assertRaises(RuntimeError):
            await ReviewState._fetch(
                None, session, "00000000-0000-0000-0000-000000000001", "scope"
            )
