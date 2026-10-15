import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import recommendation_store
import routes.recommendations as recommendation_routes


class RecommendationRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_data_dir = recommendation_store.DATA_DIR
        self.old_path = recommendation_store.RECOMMENDATIONS_PATH
        recommendation_store.DATA_DIR = Path(self.temp_dir.name)
        recommendation_store.RECOMMENDATIONS_PATH = Path(self.temp_dir.name) / "recommendations.json"
        self.app = FastAPI()
        self.app.include_router(recommendation_routes.router, prefix="/recommendations")
        self.client = TestClient(self.app)
        self.activity_patch = patch.object(recommendation_routes, "record_activity", return_value={})
        self.activity_patch.start()

    def tearDown(self):
        self.activity_patch.stop()
        recommendation_store.DATA_DIR = self.old_data_dir
        recommendation_store.RECOMMENDATIONS_PATH = self.old_path
        self.temp_dir.cleanup()

    def seed(self):
        recommendation_store.upsert_recommendations([{
            "id": "rec-test",
            "topic": "Bayes Theorem",
            "action": "Practice Quiz",
            "title": "Practice Quiz: Bayes Theorem",
            "status": "pending",
            "evidence": {"attempt_count": 3, "mastery_pct": 55, "trend": -0.1},
        }])

    def test_start_complete_and_dismiss_endpoints_persist_status(self):
        self.seed()
        started = self.client.post("/recommendations/rec-test/start")
        self.assertEqual(started.status_code, 200)
        self.assertEqual(started.json()["recommendation"]["status"], "in_progress")

        completed = self.client.post("/recommendations/rec-test/complete", json={"note": "Reviewed notes"})
        self.assertEqual(completed.status_code, 200)
        self.assertEqual(completed.json()["recommendation"]["status"], "completed")

        # A separate recommendation can be dismissed without deleting its history.
        recommendation_store.upsert_recommendations([{
            "id": "rec-dismiss",
            "topic": "SQL Joins",
            "action": "Practice Quiz",
            "status": "pending",
            "evidence": {"attempt_count": 2, "mastery_pct": 65, "trend": 0},
        }])
        dismissed = self.client.post("/recommendations/rec-dismiss/dismiss")
        self.assertEqual(dismissed.status_code, 200)
        self.assertEqual(dismissed.json()["recommendation"]["status"], "dismissed")

    def test_unknown_recommendation_returns_404(self):
        response = self.client.post("/recommendations/not-found/start")
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
