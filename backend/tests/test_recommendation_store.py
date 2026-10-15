import tempfile
import unittest
from pathlib import Path

import recommendation_store


class RecommendationStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_data_dir = recommendation_store.DATA_DIR
        self.old_path = recommendation_store.RECOMMENDATIONS_PATH
        recommendation_store.DATA_DIR = Path(self.temp_dir.name)
        recommendation_store.RECOMMENDATIONS_PATH = Path(self.temp_dir.name) / "recommendations.json"

    def tearDown(self):
        recommendation_store.DATA_DIR = self.old_data_dir
        recommendation_store.RECOMMENDATIONS_PATH = self.old_path
        self.temp_dir.cleanup()

    @staticmethod
    def row(mastery=40.0):
        return {
            "id": "rec-test",
            "topic": "Bayes Theorem",
            "action": "Deep Study",
            "status": "pending",
            "mastery_pct": mastery,
            "trend": -0.1,
            "attempts": 3,
            "evidence": {
                "attempt_count": 3,
                "question_count": 8,
                "mastery_pct": mastery,
                "trend": -0.1,
                "last_reviewed_at": "2026-10-10T00:00:00+00:00",
            },
        }

    def test_lifecycle_status_persists_across_refresh_when_evidence_unchanged(self):
        recommendation_store.upsert_recommendations([self.row()])
        started = recommendation_store.update_recommendation_status("rec-test", "in_progress")
        self.assertEqual(started["status"], "in_progress")

        same = recommendation_store.upsert_recommendations([self.row()])[0]
        self.assertEqual(same["status"], "in_progress")

        completed = recommendation_store.update_recommendation_status("rec-test", "completed")
        self.assertEqual(completed["status"], "completed")
        same = recommendation_store.upsert_recommendations([self.row()])[0]
        self.assertEqual(same["status"], "completed")

    def test_new_evidence_reopens_resolved_recommendation(self):
        recommendation_store.upsert_recommendations([self.row()])
        recommendation_store.update_recommendation_status("rec-test", "completed")
        changed = recommendation_store.upsert_recommendations([self.row(mastery=25.0)])[0]
        self.assertEqual(changed["status"], "pending")
        self.assertTrue(changed["status_history"])

    def test_unknown_recommendation_returns_none(self):
        self.assertIsNone(recommendation_store.update_recommendation_status("missing", "completed"))

    def test_reevaluated_recommendation_becomes_pending_when_it_reenters(self):
        recommendation_store.upsert_recommendations([self.row()])
        recommendation_store.upsert_recommendations([])
        hidden = recommendation_store.get_recommendation("rec-test")
        self.assertEqual(hidden["status"], "reevaluated")
        returned = recommendation_store.upsert_recommendations([self.row()])[0]
        self.assertEqual(returned["status"], "pending")

    def test_writes_are_json_and_bounded_history_is_readable(self):
        recommendation_store.upsert_recommendations([self.row()])
        self.assertTrue(recommendation_store.RECOMMENDATIONS_PATH.exists())
        rows = recommendation_store.list_recommendations(include_history=True)
        self.assertEqual(rows[0]["id"], "rec-test")

    def test_follow_up_quiz_records_matched_outcome_and_completes_recommendation(self):
        recommendation_store.upsert_recommendations([self.row(mastery=40.0)])
        outcome = recommendation_store.record_recommendation_outcome("rec-test", {
            "id": "attempt-123",
            "score": 80,
            "responses": [
                {"topic": "Bayes Theorem", "concept_id": "Conditional Probability", "is_correct": True},
                {"topic": "Bayes Theorem", "concept_id": "Conditional Probability", "is_correct": True},
                {"topic": "Bayes Theorem", "concept_id": "Conditional Probability", "is_correct": True},
                {"topic": "Bayes Theorem", "concept_id": "Conditional Probability", "is_correct": False},
            ],
        })
        # This recommendation is topic-level, so matching topic responses provide
        # the outcome measurement (not a causal claim).
        self.assertEqual(outcome["attempt_id"], "attempt-123")
        self.assertEqual(outcome["scope"], "topic")
        self.assertEqual(outcome["post_accuracy_pct"], 75.0)
        self.assertEqual(outcome["observed_change_percentage_points"], 35.0)
        saved = recommendation_store.get_recommendation("rec-test")
        self.assertEqual(saved["status"], "completed")
        self.assertEqual(saved["last_outcome"]["interpretation"],
                         "Observed follow-up performance; this comparison does not establish causation.")

    def test_mismatched_concept_is_not_claimed_as_targeted_improvement(self):
        recommendation_store.upsert_recommendations([self.row()])
        outcome = recommendation_store.record_recommendation_outcome("rec-test", {
            "id": "attempt-456",
            "score": 100,
            "responses": [
                {"topic": "Probability Basics", "concept_id": "Independent Events", "is_correct": True},
            ],
        })
        self.assertEqual(outcome["scope"], "overall_quiz_only")
        self.assertIsNone(outcome["observed_change_percentage_points"])


if __name__ == "__main__":
    unittest.main()
