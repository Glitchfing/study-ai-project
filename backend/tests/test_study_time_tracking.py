import unittest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

import activity
import routes.activity as study_routes
from fastapi import HTTPException
from routes.activity import StudySessionAction, StudySessionStart


class AccurateStudyTimeTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.log_patch = patch.object(activity, "ACTIVITY_LOG", self.events)
        self.route_log_patch = patch.object(study_routes, "ACTIVITY_LOG", self.events)
        self.save_patch = patch.object(activity, "_save_activity", return_value=None)
        self.log_patch.start()
        self.route_log_patch.start()
        self.save_patch.start()

    def tearDown(self):
        self.save_patch.stop()
        self.route_log_patch.stop()
        self.log_patch.stop()

    def test_pause_resume_excludes_paused_time_and_completion_is_idempotent(self):
        times = [
            datetime(2026, 10, 16, 10, 0, tzinfo=timezone.utc),
            datetime(2026, 10, 16, 10, 25, tzinfo=timezone.utc),
            datetime(2026, 10, 16, 10, 35, tzinfo=timezone.utc),
            datetime(2026, 10, 16, 10, 55, tzinfo=timezone.utc),
        ]
        with patch.object(study_routes, "_utc_now", side_effect=times):
            started = study_routes.start_study_session(StudySessionStart(topic="DBMS"))["session"]
            sid = started["session_id"]
            paused = study_routes.pause_study_session(StudySessionAction(session_id=sid))["session"]
            self.assertEqual(paused["status"], "paused")
            resumed = study_routes.resume_study_session(StudySessionAction(session_id=sid))["session"]
            self.assertEqual(resumed["status"], "active")
            completed = study_routes.complete_study_session(StudySessionAction(session_id=sid))["session"]
            duplicate = study_routes.complete_study_session(StudySessionAction(session_id=sid))
        self.assertEqual(completed["duration_seconds"], 45 * 60)
        self.assertEqual([item["duration_seconds"] for item in completed["intervals"]], [25 * 60, 20 * 60])
        self.assertTrue(duplicate["already_completed"])
        self.assertEqual(duplicate["session"]["duration_seconds"], 45 * 60)

    def test_invalid_transition_is_rejected(self):
        times = [
            datetime(2026, 10, 16, 10, 0, tzinfo=timezone.utc),
            datetime(2026, 10, 16, 10, 1, tzinfo=timezone.utc),
        ]
        with patch.object(study_routes, "_utc_now", side_effect=times):
            session = study_routes.start_study_session(StudySessionStart())["session"]
            sid = session["session_id"]
            study_routes.complete_study_session(StudySessionAction(session_id=sid))
            with self.assertRaises(HTTPException) as error:
                study_routes.resume_study_session(StudySessionAction(session_id=sid))
        self.assertEqual(error.exception.status_code, 409)

    def test_two_active_sessions_cannot_be_started_concurrently_in_one_store(self):
        with patch.object(study_routes, "_utc_now", return_value=datetime(2026, 10, 16, 10, 0, tzinfo=timezone.utc)):
            first = study_routes.start_study_session(StudySessionStart(topic="DBMS"))
            second = study_routes.start_study_session(StudySessionStart(topic="Python"))
        self.assertNotEqual(first["session"]["session_id"], second["session"]["session_id"])
        self.assertTrue(second["already_active"])
        self.assertEqual(second["session"]["topic"], "DBMS")

    def test_interval_duration_is_split_across_local_midnight(self):
        today = datetime.now(activity.STUDY_TZ).date()
        yesterday = today - timedelta(days=1)
        left = datetime.combine(yesterday, datetime.min.time(), tzinfo=activity.STUDY_TZ).replace(hour=23, minute=30)
        right = datetime.combine(today, datetime.min.time(), tzinfo=activity.STUDY_TZ).replace(hour=1)
        event = {
            "kind": "study_session_completed", "session_id": "midnight",
            "timestamp": right.isoformat(), "duration_seconds": 90 * 60,
            "intervals": [{"started_at": left.isoformat(), "ended_at": right.isoformat(), "duration_seconds": 90 * 60}],
        }
        with patch.object(activity, "ACTIVITY_LOG", [event]):
            self.assertEqual(activity._study_minutes_from_activity(yesterday, yesterday), 30)
            self.assertEqual(activity._study_minutes_from_activity(today, today), 60)
            cells = [cell for week in activity._activity_heatmap(18) for cell in week]
        by_date = {cell["date"]: cell for cell in cells}
        self.assertIn("1 activity", by_date[yesterday.isoformat()]["tip"])
        self.assertIn("1 activity", by_date[today.isoformat()]["tip"])

    def test_paused_intervals_are_not_included_in_dashboard_totals(self):
        event = {
            "kind": "study_session_completed", "session_id": "paused",
            "started_at": "2026-10-16T10:00:00+00:00", "ended_at": "2026-10-16T10:55:00+00:00",
            "duration_seconds": 45 * 60,
            "intervals": [
                {"started_at": "2026-10-16T10:00:00+00:00", "ended_at": "2026-10-16T10:25:00+00:00", "duration_seconds": 25 * 60},
                {"started_at": "2026-10-16T10:35:00+00:00", "ended_at": "2026-10-16T10:55:00+00:00", "duration_seconds": 20 * 60},
            ],
        }
        with patch.object(activity, "ACTIVITY_LOG", [event]):
            self.assertEqual(activity._study_minutes_from_activity(), 45)


if __name__ == "__main__":
    unittest.main()
