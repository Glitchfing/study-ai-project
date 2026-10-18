from __future__ import annotations

import unittest

from note_generation import _deduplicate_section_aids, _generation_summary


class NoteQualityUpgradeTests(unittest.TestCase):
    def test_near_duplicate_aids_are_removed_without_cross_category_loss(self):
        sections = [{
            "title": "Cloud models",
            "key_points": [
                "Cloud services provide resources over a network.",
                "Cloud services provide resources over a network!",
                "Cloud resources can scale with demand.",
            ],
            "definitions": [
                "Cloud computing delivers on-demand resources.",
            ],
            "revision_notes": [
                "Recall the service models before the exam.",
            ],
        }]
        result = _deduplicate_section_aids(sections)
        self.assertEqual(len(result[0]["key_points"]), 2)
        self.assertEqual(len(result[0]["definitions"]), 1)
        self.assertEqual(len(result[0]["revision_notes"]), 1)

    def test_generation_summary_uses_actual_section_status(self):
        sections = [
            {"generation_status": "llm", "generation_metadata": {"status": "llm"}},
            {"generation_status": "repaired", "generation_metadata": {"status": "repaired", "repair_attempts": 1}},
            {"generation_status": "fallback", "generation_metadata": {"status": "fallback", "reason": "JSONDecodeError"}},
        ]
        summary = _generation_summary(sections)
        self.assertEqual(summary["mode"], "mixed")
        self.assertEqual(summary["sections_total"], 3)
        self.assertEqual(summary["sections_llm"], 2)
        self.assertEqual(summary["sections_fallback"], 1)
        self.assertEqual(summary["sections_repaired"], 1)
        self.assertEqual(summary["fallback_reasons"], ["JSONDecodeError"])

    def test_generation_summary_does_not_call_deterministic_analysis_fallback(self):
        sections = [{"generation_status": "llm", "generation_metadata": {"status": "llm"}}]
        self.assertEqual(_generation_summary(sections)["mode"], "llm")


if __name__ == "__main__":
    unittest.main()
