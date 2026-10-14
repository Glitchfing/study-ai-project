import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import activity


class DashboardDataIntegrationTests(unittest.TestCase):
    def test_study_time_uses_completed_recorded_durations_only(self):
        now = datetime.now(activity.STUDY_TZ)
        started = (now - timedelta(minutes=37)).astimezone(activity.STUDY_TZ).isoformat()
        ended = now.isoformat()
        events = [
            {"kind": "note_view", "timestamp": now.isoformat()},
            {
                "kind": "study_session_completed",
                "session_id": "session-1",
                "started_at": started,
                "ended_at": ended,
            },
        ]
        with patch.object(activity, "ACTIVITY_LOG", events):
            self.assertEqual(activity._study_minutes_from_activity(), 37)

    def test_duplicate_completed_session_is_counted_once(self):
        now = datetime.now(activity.STUDY_TZ)
        started = (now - timedelta(minutes=20)).isoformat()
        ended = now.isoformat()
        one = {
            "kind": "study_session_completed",
            "session_id": "session-duplicate",
            "started_at": started,
            "ended_at": ended,
        }
        duplicate = {**one, "event_id": "duplicate-retry"}
        with patch.object(activity, "ACTIVITY_LOG", [one, duplicate]):
            self.assertEqual(activity._study_minutes_from_activity(), 20)

    def test_study_time_range_uses_ist_calendar_days(self):
        # 23:30 IST on Oct 14 through 01:00 IST on Oct 15.
        event = {
            "kind": "study_session_completed",
            "session_id": "cross-midnight",
            "started_at": "2026-10-14T18:00:00+00:00",
            "ended_at": "2026-10-14T19:30:00+00:00",
        }
        with patch.object(activity, "ACTIVITY_LOG", [event]):
            self.assertEqual(activity._study_minutes_from_activity(
                datetime(2026, 10, 14).date(), datetime(2026, 10, 14).date()
            ), 30)
            self.assertEqual(activity._study_minutes_from_activity(
                datetime(2026, 10, 15).date(), datetime(2026, 10, 15).date()
            ), 60)

    def test_heatmap_ignores_dashboard_open_events(self):
        today = datetime.now(activity.STUDY_TZ).date()
        event = {"kind": "dashboard_opened", "timestamp": datetime.now(activity.STUDY_TZ).isoformat()}
        with patch.object(activity, "ACTIVITY_LOG", [event]):
            cells = [cell for week in activity._activity_heatmap(1) for cell in week]
        today_cell = next(cell for cell in cells if cell["date"] == today.isoformat())
        self.assertEqual(today_cell["tip"], "No activity")
        self.assertEqual(today_cell["lvl"], "")

    def test_activity_events_persist_and_retries_are_idempotent(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            log_path = data_dir / "activity_events.json"
            with patch.object(activity, "DATA_DIR", data_dir), \
                 patch.object(activity, "ACTIVITY_PATH", log_path), \
                 patch.object(activity, "ACTIVITY_LOG", []):
                activity.record_activity("quiz_completed", attempt_id="attempt-123", score=80)
                activity.record_activity("quiz_completed", attempt_id="attempt-123", score=80)
                saved = json.loads(log_path.read_text(encoding="utf-8"))
                self.assertEqual(len(saved), 1)
                self.assertEqual(saved[0]["score"], 80)


if __name__ == "__main__":
    unittest.main()
