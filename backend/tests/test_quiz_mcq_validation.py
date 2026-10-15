import unittest

from services.intelligent_quiz_generator import _valid_mcq
from quiz_engine import _distinct_mcq_options, _normalize_answer, _normalize_question


class QuizMcqValidationTests(unittest.TestCase):
    def test_mcq_answer_matches_option_despite_punctuation_and_case(self):
        question = {
            "type": "mcq",
            "question": "Which statement best describes machine learning?",
            "options": [
                "A system learns patterns from data.",
                "A database stores records.",
                "A compiler translates source code.",
                "A network routes packets.",
            ],
            "correct_answer": "a system learns patterns from data",
            "explanation": "The notes describe machine learning as learning patterns from data.",
        }
        self.assertTrue(_valid_mcq(question))

    def test_normalized_duplicate_options_are_not_counted_as_four_distinct_options(self):
        options = _distinct_mcq_options(["Answer A", "answer a!", "Answer B", "Answer C", "Answer D"])
        self.assertEqual(len(options), 4)

    def test_quiz_normalizer_canonicalizes_correct_answer_to_option(self):
        question = _normalize_question({
            "type": "mcq",
            "question": "Which statement best describes machine learning?",
            "options": ["Learn patterns from data.", "Store records.", "Compile code.", "Route packets."],
            "correct_answer": "learn patterns from data",
            "explanation": "It learns patterns from examples.",
        }, index=1, note_id="ml-models", note_title="ML Models Overview")
        self.assertEqual(question["correct_answer"], "Learn patterns from data.")
        self.assertEqual(
            _normalize_answer(question["options"][question["correct"]]),
            _normalize_answer(question["correct_answer"]),
        )

    def test_four_options_still_required(self):
        question = {
            "type": "mcq",
            "question": "Which statement best describes machine learning?",
            "options": ["A", "B", "C"],
            "correct_answer": "A",
            "explanation": "Explanation.",
        }
        self.assertFalse(_valid_mcq(question))


if __name__ == "__main__":
    unittest.main()
