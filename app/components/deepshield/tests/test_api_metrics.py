import reflex as rx

import unittest
from fastapi.testclient import TestClient
from app.components.deepshield.api import create_api
from app.components.deepshield.config import Settings
from app.components.deepshield.evaluation.metrics import metrics
from app.components.deepshield.service import DetectionService


class BoundaryTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_api(DetectionService(Settings())))

    def test_health_does_not_load_models(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["models"]["image"], "not_loaded")

    def test_all_detection_routes_registered(self):
        for modality in ("image", "video", "audio", "text", "multimodal"):
            response = self.client.post(f"/detect/{modality}", json={})
            self.assertEqual(response.status_code, 422)
            self.assertEqual(response.json()["status"], "invalid_input")

    def test_invalid_base64(self):
        response = self.client.post(
            "/detect/image", json={"data_base64": "!!!!"}
        )
        result = response.json()["results"][0]
        self.assertEqual(result["status"], "invalid_input")
        self.assertIsNone(result["score"])

    def test_single_class_metrics_are_explicitly_undefined(self):
        result = metrics([0, 0], [0.1, 0.2], audio=True)
        self.assertIsNone(result["roc_auc"])
        self.assertIsNone(result["eer"])

    def test_metric_formulas_with_unit_test_fixture(self):
        result = metrics([0, 0, 1, 1], [0.1, 0.8, 0.2, 0.9], audio=True)
        self.assertEqual(result["confusion_matrix"], [[1, 1], [1, 1]])
        self.assertEqual(result["accuracy"], 0.5)
        self.assertEqual(result["FAR"], 0.5)
        self.assertEqual(result["FRR"], 0.5)


if __name__ == "__main__":
    unittest.main()
