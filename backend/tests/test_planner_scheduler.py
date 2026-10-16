import unittest
from datetime import datetime, timedelta, timezone

from routes.planner import calculate_priority, _duration, _overlap


class RevisionSchedulerUnitTests(unittest.TestCase):
    def test_weak_topic_has_higher_priority_than_strong_topic(self):
        now = datetime(2026, 10, 16, 10, tzinfo=timezone.utc)
        weak, _ = calculate_priority(
            {"mastery": 0.25, "trend_label": "stable", "evidence_confidence": 0.8},
            now=now, due_at=None, importance=0.5,
        )
        strong, _ = calculate_priority(
            {"mastery": 0.92, "trend_label": "stable", "evidence_confidence": 1.0},
            now=now, due_at=None, importance=0.5,
        )
        self.assertGreater(weak, strong)

    def test_declining_performance_increases_priority(self):
        now = datetime(2026, 10, 16, 10, tzinfo=timezone.utc)
        stable, _ = calculate_priority(
            {"mastery": 0.7, "trend_label": "stable", "trend": 0.0, "evidence_confidence": 0.8},
            now=now, due_at=None,
        )
        declining, factors = calculate_priority(
            {"mastery": 0.7, "trend_label": "declining", "trend": -0.2, "evidence_confidence": 0.8},
            now=now, due_at=None,
        )
        self.assertGreater(declining, stable)
        self.assertGreater(factors["decline"], 0)

    def test_approaching_deadline_increases_urgency(self):
        now = datetime(2026, 10, 16, 10, tzinfo=timezone.utc)
        far, far_factors = calculate_priority(
            {"mastery": 0.7, "trend_label": "stable", "evidence_confidence": 0.8},
            now=now, due_at=now + timedelta(days=12),
        )
        soon, soon_factors = calculate_priority(
            {"mastery": 0.7, "trend_label": "stable", "evidence_confidence": 0.8},
            now=now, due_at=now + timedelta(hours=4),
        )
        self.assertGreater(soon, far)
        self.assertGreater(soon_factors["urgency"], far_factors["urgency"])

    def test_missing_mastery_is_not_treated_as_measured_weakness(self):
        now = datetime(2026, 10, 16, 10, tzinfo=timezone.utc)
        score, factors = calculate_priority(
            {"mastery": None, "trend_label": "insufficient_data", "evidence_confidence": 0},
            now=now, due_at=None,
        )
        self.assertEqual(factors["weakness"], 0)
        self.assertEqual(factors["decline"], 0)
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 1)

    def test_duration_parsing_uses_existing_estimate(self):
        self.assertEqual(_duration({"est": "25 min"}), 25)
        self.assertEqual(_duration({"est": "2h"}), 120)
        self.assertEqual(_duration({"duration_minutes": 35, "est": "20 min"}), 35)

    def test_overlap_uses_scheduled_time_not_due_date(self):
        scheduled = datetime(2026, 10, 17, 12, tzinfo=timezone.utc)
        task = {"due_date": scheduled.isoformat(), "duration_minutes": 30}
        self.assertFalse(_overlap(scheduled, 20, task))
        task["scheduled_at"] = (scheduled + timedelta(minutes=10)).isoformat()
        self.assertTrue(_overlap(scheduled, 20, task))


if __name__ == "__main__":
    unittest.main()
