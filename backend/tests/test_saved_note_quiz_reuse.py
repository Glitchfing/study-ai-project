from __future__ import annotations

import unittest
from unittest.mock import patch

from quiz_engine import _canonicalize_saved_mcq, generate_quiz_for_package


class SavedNoteQuizReuseTests(unittest.TestCase):
    def test_saved_note_mcq_is_reused_without_calling_generator(self):
        question = {
            "type": "mcq",
            "question": "Which statement best describes cloud elasticity?",
            "options": [
                "Resources scale with changing demand",
                "Resources are permanently fixed",
                "Only local hardware can be used",
                "All services must run offline",
            ],
            "correct_answer": "Resources scale with changing demand",
            "explanation": "Elasticity adjusts allocated resources as workload demand changes.",
            "difficulty": "medium",
            "topic": "Cloud Computing",
        }
        package = {
            "requested_topic": "",
            "questions": [question],
            "sections": [],
        }
        with patch("quiz_engine.generate_exam_style_questions") as generate:
            result = generate_quiz_for_package(
                package,
                note_id=None,
                note_title="Cloud Computing Module One",
                limit=1,
            )
        generate.assert_not_called()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["question"], question["question"])
        self.assertEqual(len(result[0]["options"]), 4)
        self.assertIn(result[0]["correct_answer"], result[0]["options"])

    def test_legacy_index_answer_schema_is_normalized(self):
        question = {
            "question_type": "multiple_choice",
            "question_text": "Which option correctly describes cloud scalability?",
            "choices": [
                "Adding resources to meet demand",
                "Removing all network access",
                "Using only one fixed server",
                "Disabling resource monitoring",
            ],
            "answer_index": 0,
            "rationale": "Scalability allows capacity to increase as workload grows.",
        }
        normalized = _canonicalize_saved_mcq(question)
        self.assertIsNotNone(normalized)
        self.assertEqual(normalized["type"], "mcq")
        self.assertEqual(normalized["correct_answer"], normalized["options"][0])

    def test_section_level_saved_questions_are_reused(self):
        question = {
            "type": "mcq",
            "question": "Which statement best describes cloud availability?",
            "options": [
                "Services remain accessible when required",
                "Every service runs without a network",
                "Storage never needs maintenance",
                "All requests are processed offline",
            ],
            "correct_answer": "Services remain accessible when required",
            "explanation": "Availability describes whether a service is accessible when users need it.",
        }
        package = {
            "questions": [],
            "sections": [{"title": "Availability", "questions": [question]}],
        }
        with patch("quiz_engine.generate_exam_style_questions") as generate:
            result = generate_quiz_for_package(
                package,
                note_id=None,
                note_title="Cloud Computing",
                limit=1,
            )
        generate.assert_not_called()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["correct_answer"], question["correct_answer"])


if __name__ == "__main__":
    unittest.main()
