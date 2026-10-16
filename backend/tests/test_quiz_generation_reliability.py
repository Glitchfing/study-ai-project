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
        with patch.object(quiz, "generate_structured_json", return_value={"questions": []}) as generate:
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


if __name__ == "__main__":
    unittest.main()
