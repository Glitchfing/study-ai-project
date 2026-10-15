import unittest
from datetime import datetime, timezone

from recommendation_service import build_recommendations


class RecommendationServiceTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 16, 0, 0, tzinfo=timezone.utc)

    def test_insufficient_history_recommends_diagnostic_not_confident_weakness(self):
        rows = build_recommendations(
            {"Bayes Theorem": {
                "mastery_pct": 20.0,
                "trend": None,
                "trend_label": "insufficient_data",
                "attempts": 1,
                "question_count": 5,
                "evidence_confidence": 0.2,
                "last_reviewed_at": None,
            }},
            now=self.now,
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["action"], "Practice Quiz")
        self.assertEqual(rows[0]["type"], "diagnostic")
        self.assertIn("not enough quiz history", rows[0]["reason"])
        self.assertNotIn("overdue", rows[0]["reason"])

    def test_explicit_concept_evidence_produces_specific_recommendation(self):
        rows = build_recommendations(
            {"Bayes Theorem": {
                "mastery_pct": 66.0,
                "trend": -0.1,
                "attempts": 4,
                "question_count": 20,
                "evidence_confidence": 0.8,
                "last_reviewed_at": "2026-10-10T00:00:00+00:00",
            }},
            concept_mastery={"Conditional Probability": {
                "topic": "Bayes Theorem",
                "mastery_pct": 35.0,
                "trend": -0.2,
                "trend_label": "declining",
                "attempts": 3,
                "question_count": 5,
                "incorrect_count": 4,
                "evidence_confidence": 1.0,
                "last_reviewed_at": "2026-10-12T00:00:00+00:00",
            }},
            now=self.now,
        )
        self.assertEqual(rows[0]["concept"], "Conditional Probability")
        self.assertEqual(rows[0]["evidence_level"], "concept")
        self.assertIn("Conditional Probability", rows[0]["reason"])
        self.assertEqual(rows[0]["evidence"]["incorrect_count"], 4)

    def test_missing_review_timestamp_is_not_treated_as_overdue(self):
        missing = build_recommendations(
            {"SQL Joins": {
                "mastery_pct": 90.0, "trend": 0.0, "attempts": 5,
                "evidence_confidence": 1.0, "last_reviewed_at": None,
            }},
            now=self.now,
        )[0]
        old = build_recommendations(
            {"SQL Joins": {
                "mastery_pct": 90.0, "trend": 0.0, "attempts": 5,
                "evidence_confidence": 1.0, "last_reviewed_at": "2026-10-01T00:00:00+00:00",
            }},
            now=self.now,
        )[0]
        self.assertLess(missing["priority_score"], old["priority_score"])
        self.assertNotIn("day(s) ago", missing["reason"])

    def test_recommendation_id_is_stable_for_same_learning_need(self):
        model = {"SQL Joins": {"mastery_pct": 55, "trend": 0.0, "attempts": 3, "evidence_confidence": 0.6}}
        first = build_recommendations(model, now=self.now)[0]
        second = build_recommendations(model, now=self.now)[0]
        self.assertEqual(first["id"], second["id"])

    def test_weights_are_validated(self):
        with self.assertRaises(ValueError):
            build_recommendations({}, weights={"weakness": 1.0})


if __name__ == "__main__":
    unittest.main()
