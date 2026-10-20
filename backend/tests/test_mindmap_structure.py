from __future__ import annotations

import unittest

from services.educational_note_generator import _mindmap


class MindMapStructureTests(unittest.TestCase):
    def test_mindmap_uses_study_aids_for_meaningful_radial_branches(self):
        result = _mindmap(
            "Database Management",
            ["properties", "incorrectly", "common", "data", "then"],
            study_aids={
                "key_points": [
                    "Functional dependencies support database normalization",
                    "BCNF prevents certain update anomalies",
                ],
                "definitions": [
                    "Functional dependency means one attribute determines another attribute",
                ],
                "examples": [
                    "BCNF requires every determinant to be a superkey",
                ],
                "important_notes": [
                    "Normalization reduces duplication and update anomalies",
                ],
            },
        )

        labels = [branch["name"].casefold() for branch in result["branches"]]
        self.assertGreaterEqual(len(labels), 2)
        self.assertTrue(any("functional dependencies" in label for label in labels))
        self.assertTrue(any("bcnf" in label for label in labels))
        self.assertFalse(any(label in {"properties", "incorrectly", "common", "data", "then"} for label in labels))
        self.assertTrue(any(branch["sub_branches"] for branch in result["branches"]))
        self.assertTrue(result["mermaid"].startswith("mindmap\n"))
        self.assertIn("root((", result["mermaid"])

    def test_keyword_fallback_prefers_complete_source_sentences(self):
        result = _mindmap(
            "Database Management",
            ["properties", "incorrectly", "common", "data", "then"],
            source_content=(
                "Database normalization organizes tables to reduce duplication. "
                "Functional dependencies describe relationships between attributes."
            ),
        )

        labels = [branch["name"].casefold() for branch in result["branches"]]
        self.assertTrue(labels)
        self.assertTrue(any("normalization" in label for label in labels))
        self.assertTrue(any("functional dependencies" in label for label in labels))
        self.assertFalse(any(label in {"properties", "incorrectly", "common", "data", "then"} for label in labels))


if __name__ == "__main__":
    unittest.main()
