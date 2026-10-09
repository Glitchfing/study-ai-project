import unittest
from datetime import datetime, timezone

from learner_model import build_topic_mastery, calculate_mastery
from recommendation_service import build_recommendations


class LearnerModelTests(unittest.TestCase):
    def test_empty_history_has_no_mastery(self):
        self.assertIsNone(calculate_mastery([]))
        self.assertEqual(build_topic_mastery([]), {})

    def test_single_score_is_mastery(self):
        self.assertAlmostEqual(calculate_mastery([0.72]), 0.72)

    def test_recency_weighting_gives_newer_score_more_weight(self):
        result = calculate_mastery([1.0, 0.2], decay=0.85)
        expected = ((1.0 * 0.85) + (0.2 * 1.0)) / 1.85
        self.assertAlmostEqual(result, expected)
        self.assertLess(result, 0.6)

    def test_decay_parameter_is_validated(self):
        with self.assertRaises(ValueError):
            calculate_mastery([0.5], decay=0)
        with self.assertRaises(ValueError):
            calculate_mastery([1.1])

    def test_attempts_are_sorted_chronologically(self):
        attempts = [
            {"topic": "NLP", "score": 20, "created_at": "2026-01-02T10:00:00"},
            {"topic": "NLP", "score": 100, "created_at": "2026-01-01T10:00:00"},
        ]
        summary = build_topic_mastery(attempts)
        # Newer 20% score is weighted more heavily than the older 100% score.
        self.assertAlmostEqual(summary["NLP"]["mastery_pct"], 56.8, places=1)
        self.assertLess(summary["NLP"]["trend"], 0)

    def test_response_level_topics_override_generic_generated_label(self):
        attempts = [{
            "topic": "generated",
            "topic_label": "Generated Quiz",
            "score": 50,
            "created_at": "2026-01-01T10:00:00",
            "responses": [
                {"topic": "Bayes Theorem", "is_correct": True},
                {"topic": "Bayes Theorem", "is_correct": False},
                {"topic": "Conditional Probability", "is_correct": True},
            ],
        }]
        summary = build_topic_mastery(attempts)
        self.assertAlmostEqual(summary["Bayes Theorem"]["mastery_pct"], 50.0)
        self.assertAlmostEqual(summary["Conditional Probability"]["mastery_pct"], 100.0)
        self.assertNotIn("Generated Quiz", summary)

    def test_generic_quiz_without_topic_metadata_is_not_mislabelled(self):
        attempts = [{
            "topic": "generated",
            "topic_label": "Generated Quiz",
            "score": 50,
            "created_at": "2026-01-01T10:00:00",
        }]
        self.assertEqual(build_topic_mastery(attempts), {})

    def test_stored_score_of_one_means_one_percent(self):
        summary = build_topic_mastery([{
            "topic": "NLP",
            "score": 1,
            "created_at": "2026-01-01T10:00:00",
        }])
        self.assertAlmostEqual(summary["NLP"]["mastery_pct"], 1.0)

    def test_recommendations_are_ranked_and_have_review_intervals(self):
        now = datetime(2026, 10, 9, tzinfo=timezone.utc)
        model = {
            "Weak topic": {
                "mastery_pct": 35.0, "trend": -0.2,
                "last_reviewed_at": "2026-09-20T00:00:00+00:00",
            },
            "Strong topic": {
                "mastery_pct": 92.0, "trend": 0.1,
                "last_reviewed_at": "2026-10-08T00:00:00+00:00",
            },
        }
        result = build_recommendations(model, now=now)
        self.assertEqual(len(result), 2)
        self.assertGreaterEqual(result[0]["priority"], result[1]["priority"])
        self.assertEqual(result[0]["topic"], "Weak topic")
        self.assertEqual(result[0]["next_review_days"], 1)

    def test_recommendation_weights_must_sum_to_one(self):
        with self.assertRaises(ValueError):
            build_recommendations({}, weights={
                "weakness": 0.5, "decline": 0.2,
                "urgency": 0.2, "utility": 0.2,
            })


if __name__ == "__main__":
    unittest.main()
