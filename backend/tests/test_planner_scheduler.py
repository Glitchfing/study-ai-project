import unittest
from fastapi import HTTPException
from datetime import datetime, timedelta, timezone

from routes.planner import calculate_priority, _duration, _overlap, _eligible_slots, STUDY_TZ


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


    def test_schedule_generation_persists_times_and_is_idempotent(self):
        from contextlib import ExitStack
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        from routes import planner

        fixed_now = datetime(2026, 10, 16, 10, 0, tzinfo=timezone.utc)
        candidate = [{
            "topic": "Topic A",
            "stats": {"mastery": 0.45, "trend_label": "stable", "evidence_confidence": 0.6},
            "priority_score": 0.55,
            "factors": {"weakness": 0.55, "decline": 0, "urgency": 0, "importance": 0.5, "uncertainty": 0.4},
            "activity_type": "targeted_practice",
            "title": "Targeted revision: Topic A",
            "duration_minutes": 20,
            "reason": "Measured mastery 45%",
            "due_at": None,
        }]
        with TemporaryDirectory() as temp:
            root = Path(temp)
            with ExitStack() as stack:
                stack.enter_context(patch.object(planner, "TASKS", []))
                stack.enter_context(patch.object(planner, "TASKS_PATH", root / "revision_tasks.json"))
                stack.enter_context(patch.object(planner, "DATA_DIR", root))
                stack.enter_context(patch.object(planner, "_utc_now", return_value=fixed_now))
                stack.enter_context(patch.object(planner, "_candidate_topics", return_value=candidate))
                stack.enter_context(patch.object(planner, "_read_preferences", return_value={
                    "daily_minutes": 60, "planning_days": 7,
                    "preferred_start_hour": 18, "preferred_end_hour": 22,
                    "topic_importance": {}, "deadlines": [],
                }))
                stack.enter_context(patch.object(planner, "record_activity"))
                first = planner.auto_schedule()
                first_snapshot = (root / "revision_tasks.json").read_text(encoding="utf-8")
                second = planner.auto_schedule()
                second_snapshot = (root / "revision_tasks.json").read_text(encoding="utf-8")

        self.assertEqual(first["created_count"], 1)
        self.assertEqual(len(first["tasks"]), 1)
        self.assertTrue(first["tasks"][0].get("scheduled_at"))
        self.assertEqual(second["created_count"], 0)
        self.assertEqual(len(second["tasks"]), 1)
        self.assertEqual(first_snapshot, second_snapshot)


    def test_eligible_slots_respect_selected_weekdays(self):
        now = datetime(2026, 10, 16, 10, 0, tzinfo=timezone.utc)
        slots = _eligible_slots({
            "preferred_start_hour": 18,
            "preferred_end_hour": 20,
            "available_days": [0, 2, 4],
        }, now, 14)
        self.assertTrue(slots)
        self.assertTrue(all(slot.astimezone(STUDY_TZ).weekday() in {0, 2, 4} for slot in slots))

    def test_rescheduling_rejects_overlapping_revision_tasks(self):
        from contextlib import ExitStack
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        from routes import planner

        fixed = "2030-04-11T18:00:00+05:30"
        tasks = [
            {"id": 1, "title": "First", "topic": "A", "status": "planned", "done": False, "scheduled_at": "2030-04-11T12:30:00+00:00", "duration_minutes": 30},
            {"id": 2, "title": "Second", "topic": "B", "status": "planned", "done": False, "scheduled_at": "2030-04-11T12:45:00+00:00", "duration_minutes": 30},
        ]
        with TemporaryDirectory() as temp:
            with ExitStack() as stack:
                stack.enter_context(patch.object(planner, "TASKS", tasks))
                stack.enter_context(patch.object(planner, "TASKS_PATH", Path(temp) / "revision_tasks.json"))
                stack.enter_context(patch.object(planner, "DATA_DIR", Path(temp)))
                stack.enter_context(patch.object(planner, "_read_preferences", return_value={
                    "daily_minutes": 180, "preferred_start_hour": 9, "preferred_end_hour": 23, "available_days": list(range(7)),
                }))
                stack.enter_context(patch.object(planner, "record_activity"))
                with self.assertRaises(HTTPException) as raised:
                    planner.update_task("1", planner.TaskEdit(scheduled_at=fixed))
        self.assertEqual(raised.exception.status_code, 409)
        self.assertIn("overlaps", raised.exception.detail)

    def test_cancel_task_is_a_soft_cancel_and_idempotent(self):
        from contextlib import ExitStack
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        from routes import planner

        task = {"id": 1, "title": "Review topic", "topic": "Topic A", "status": "planned", "done": False}
        with TemporaryDirectory() as temp:
            with ExitStack() as stack:
                stack.enter_context(patch.object(planner, "TASKS", [task]))
                stack.enter_context(patch.object(planner, "TASKS_PATH", Path(temp) / "revision_tasks.json"))
                stack.enter_context(patch.object(planner, "DATA_DIR", Path(temp)))
                stack.enter_context(patch.object(planner, "record_activity"))
                first = planner.cancel_task("1")
                second = planner.cancel_task("1")
                self.assertEqual(first["task"]["status"], "cancelled")
                self.assertTrue(second["already_cancelled"])
                self.assertTrue((Path(temp) / "revision_tasks.json").exists())



if __name__ == "__main__":
    unittest.main()
