from __future__ import annotations

import unittest

from note_generation import _aggregate_mindmap


class RadialMindMapAggregationTests(unittest.TestCase):
    def test_aggregate_map_uses_grounded_phrases_not_keyword_fragments(self):
        result = _aggregate_mindmap(
            [{
                "title": "Data Warehouse Architecture",
                "topics": ["data", "then", "warehouse", "common", "incorrectly"],
                "concept_keywords": ["data", "key"],
                "key_points": [
                    "A data warehouse integrates data from multiple sources.",
                    "Dimensional modeling organizes facts and dimensions.",
                ],
                "definitions": [
                    "A fact table stores measurable events in a data warehouse.",
                ],
                "examples": [
                    "Star schema organizes a central fact table with dimension tables.",
                ],
            }],
            "Database Systems",
        )

        self.assertTrue(result["mermaid"].startswith("mindmap\n"))
        self.assertIn("root((Database Systems))", result["mermaid"])
        self.assertEqual(len(result["branches"]), 1)
        self.assertEqual(result["branches"][0]["name"], "Data Warehouse Architecture")
        child_labels = [child["name"].casefold() for child in result["branches"][0]["sub_branches"]]
        self.assertTrue(child_labels)
        self.assertTrue(any("data warehouse" in label for label in child_labels))
        self.assertFalse(any(label in {"data", "then", "warehouse", "common", "incorrectly", "key"} for label in child_labels))
        self.assertTrue(all(len(label.split()) >= 2 or label.isupper() for label in child_labels))


    def test_sentence_length_is_compacted_for_radial_layout(self):
        result = _aggregate_mindmap(
            [{
                "title": "Business Intelligence and Data Analytics",
                "key_points": [
                    "The business intelligence platform enables organizations to monitor business performance through analytical dashboards.",
                    "A data warehouse provides an integrated, cleaned, standardized view of organizational data from multiple sources.",
                    "Business performance management links business metrics to strategy, objectives, and action planning.",
                ],
                "definitions": [
                    "Business intelligence: techniques for transforming raw data into actionable insights.",
                ],
            }],
            "BIDA",
        )

        labels = [branch["name"] for branch in result["branches"]]
        labels.extend(
            child["name"]
            for branch in result["branches"]
            for child in branch["sub_branches"]
        )
        self.assertTrue(labels)
        self.assertTrue(all(len(label) <= 38 for label in labels))
        self.assertFalse(any(
            action in label.casefold()
            for label in labels
            for action in (" enables ", " provides ", " links ")
        ))
        self.assertTrue(any("data warehouse" in label.casefold() for label in labels))

if __name__ == "__main__":
    unittest.main()
