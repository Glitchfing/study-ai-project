from __future__ import annotations

import unittest
from unittest.mock import patch

from services import intelligent_quiz_generator as quiz


class QuizGenerationReliabilityTests(unittest.TestCase):
    def _prose_package(self):
        return {
            "document_title": "Cybersecurity notes",
            "sections": [
                {
                    "title": "Security principles",
                    "topics": ["Cybersecurity"],
                    "content": (
                        "Confidentiality protects sensitive information from unauthorized access or disclosure in a computer system. "
                        "Integrity ensures that stored information remains accurate, complete, and unchanged unless authorized. "
                        "Availability enables authorized users to access systems and data when needed. "
                        "Authentication verifies a user's identity before a system grants access to protected resources."
                    ),
                }
            ],
        }

    def test_llm_prompt_is_bounded_and_uses_requested_candidate_count(self):
        package = {
            "document_title": "Large note",
            "sections": [{"title": "Section", "content": "Important learning fact. " * 12000}],
        }
        with patch.object(quiz, "generate_structured_json", return_value={"questions": [{"type": "mcq"}]}) as generate:
            quiz._llm_candidates(package, 12)
        prompt = generate.call_args.args[1]
        self.assertIn("Need 12 candidate questions before filtering.", prompt)
        self.assertLess(len(prompt), 22000)

    def test_compaction_prioritizes_the_requested_topic(self):
        package = {
            "quiz_topic": "tokenization",
            "sections": [
                {"title": "Servlet basics", "topics": ["Java"], "content": "Servlet lifecycle handles web requests."},
                {"title": "Tokenization", "topics": ["NLP tokenization"], "content": "Tokenization splits text into tokens."},
            ],
        }
        sections = quiz._compact_section_payload(package, max_chars=1000)
        self.assertGreaterEqual(len(sections), 1)
        self.assertEqual(sections[0]["title"], "Tokenization")

    def test_fallback_generates_only_grounded_four_option_mcqs_from_prose(self):
        candidates = quiz._fallback_candidates(self._prose_package(), limit=5)
        self.assertGreaterEqual(len(candidates), 1)
        for question in candidates:
            self.assertTrue(quiz._valid_mcq(question))
            self.assertEqual(len(question["options"]), 4)
            self.assertIn(question["correct_answer"], question["options"])
            self.assertTrue(question["explanation"])

    def test_empty_llm_output_uses_source_note_fallback(self):
        with patch.object(quiz, "has_llm_support", return_value=True), patch.object(
            quiz, "_llm_candidates", return_value=[]
        ):
            questions = quiz.generate_exam_style_questions(self._prose_package(), limit=3)
        self.assertGreaterEqual(len(questions), 1)
        self.assertTrue(all(quiz._valid_mcq(question) for question in questions))

    def test_malformed_structured_output_is_retried(self):
        good_payload = {"questions": [{"type": "mcq", "question": "A valid question?"}]}
        with patch.object(
            quiz,
            "generate_structured_json",
            side_effect=[ValueError("JSONDecodeError: Expecting ',' delimiter"), good_payload],
        ) as generate:
            result = quiz._generate_quiz_payload_with_retry("system", "same source and topic")
        self.assertEqual(result, good_payload)
        self.assertEqual(generate.call_count, 2)
        self.assertEqual(generate.call_args.args[1], "same source and topic")

    def test_undersized_provider_batch_is_retried_and_best_batch_kept(self):
        smaller = {"questions": [{"type": "mcq", "question": "Question one?"}]}
        larger = {"questions": [{"type": "mcq", "question": f"Question {i}?"} for i in range(3)]}
        with patch.object(
            quiz,
            "generate_structured_json",
            side_effect=[smaller, larger],
        ) as generate:
            result = quiz._generate_quiz_payload_with_retry(
                "system",
                "same source and topic",
                expected_count=4,
            )
        self.assertEqual(len(result["questions"]), 3)
        self.assertEqual(generate.call_count, 2)

    def test_empty_source_does_not_call_llm(self):
        package = {"document_title": "Title only", "sections": []}
        with patch.object(quiz, "has_llm_support", return_value=True), patch.object(
            quiz, "_llm_candidates"
        ) as generate:
            self.assertEqual(quiz.generate_exam_style_questions(package, limit=5), [])
        generate.assert_not_called()

    def test_targeted_note_generation_rejects_empty_context(self):
        from services import targeted_note_generation as target_notes

        with patch.object(target_notes, "run_targeted_note_pipeline") as generate:
            with self.assertRaisesRegex(ValueError, "without retrieved source text"):
                target_notes.generate_targeted_note_package(
                    context="",
                    topic="Tokenization",
                    source_metadata={"filename": "nlp.pdf"},
                )
        generate.assert_not_called()

    def test_quiz_sets_are_persisted_per_note_and_topic(self):
        from note_store import GENERATED_NOTES, get_saved_quiz_set, save_quiz_set

        note_id = "quiz-cache-test-note"
        questions = [{"id": "q1", "type": "mcq", "options": ["A", "B", "C", "D"]}]
        with patch.dict(GENERATED_NOTES, {note_id: {"id": note_id, "package": {}}}), patch(
            "note_store._save_generated_notes"
        ) as save:
            self.assertTrue(save_quiz_set(note_id, "Tokenization", questions))
            stored = get_saved_quiz_set(note_id, "tokenization")
            self.assertIsNotNone(stored)
            self.assertEqual(stored["topic"], "Tokenization")
            self.assertEqual(stored["questions"], questions)
            self.assertIsNone(get_saved_quiz_set(note_id, "BERT"))
            save.assert_called_once()

    def test_saved_note_quiz_is_reused_when_scope_matches(self):
        from quiz_engine import generate_quiz_for_package

        package = {
            "document_title": "Cybersecurity",
            "requested_topic": "Cybersecurity",
            "requested_quiz_topic": "Cybersecurity",
            "quiz_topic": "Cybersecurity",
            "sections": [{"title": "Security principles", "content": "Security concepts for testing."}],
            "questions": [
                {
                    "type": "mcq",
                    "question": "Which security property protects private information from unauthorized disclosure?",
                    "options": [
                        "Confidentiality protects private information.",
                        "Integrity keeps information accurate.",
                        "Availability keeps systems accessible.",
                        "Authentication verifies user identity.",
                    ],
                    "correct_answer": "Confidentiality protects private information.",
                    "explanation": "Confidentiality prevents unauthorized disclosure of sensitive information.",
                    "difficulty": "easy",
                    "topic": "Confidentiality",
                },
                {
                    "type": "mcq",
                    "question": "Which security property keeps stored information accurate and unchanged without authorization?",
                    "options": [
                        "Confidentiality protects private information.",
                        "Integrity keeps information accurate.",
                        "Availability keeps systems accessible.",
                        "Authentication verifies user identity.",
                    ],
                    "correct_answer": "Integrity keeps information accurate.",
                    "explanation": "Integrity protects the correctness and completeness of stored information.",
                    "difficulty": "medium",
                    "topic": "Integrity",
                },
            ],
        }
        with patch("quiz_engine._question_memory", return_value=[]), patch(
            "quiz_engine.generate_exam_style_questions",
            side_effect=AssertionError("saved quiz should be reused without an LLM call"),
        ):
            questions = generate_quiz_for_package(
                package,
                note_id="saved-note-1",
                note_title="Cybersecurity",
                limit=2,
            )
        self.assertEqual(len(questions), 2)
        self.assertTrue(all(len(question["options"]) == 4 for question in questions))
        self.assertTrue(all(question["note_id"] == "saved-note-1" for question in questions))


if __name__ == "__main__":
    unittest.main()
