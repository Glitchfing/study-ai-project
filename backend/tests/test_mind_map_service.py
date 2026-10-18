import unittest

from services.mind_map_service import _fallback_map, _validate_map


class MindMapValidationTests(unittest.TestCase):
    def test_valid_hierarchy_adds_parent_edges(self):
        result = _validate_map(
            {
                "nodes": [
                    {"id": "root", "parent_id": None, "label": "Databases", "type": "topic"},
                    {"id": "sql", "parent_id": "root", "label": "SQL", "type": "concept"},
                    {"id": "joins", "parent_id": "sql", "label": "Joins", "type": "detail"},
                ],
                "edges": [],
            },
            "Databases",
        )
        self.assertEqual(len(result["nodes"]), 3)
        self.assertEqual({(edge["source"], edge["target"]) for edge in result["edges"]}, {("root", "sql"), ("sql", "joins")})

    def test_duplicate_ids_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            _validate_map(
                {"nodes": [
                    {"id": "root", "parent_id": None, "label": "Root"},
                    {"id": "root", "parent_id": "root", "label": "Duplicate"},
                ]},
                "Root",
            )

    def test_cycles_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "cycle"):
            _validate_map(
                {"nodes": [
                    {"id": "root", "parent_id": None, "label": "Root"},
                    {"id": "a", "parent_id": "b", "label": "A"},
                    {"id": "b", "parent_id": "a", "label": "B"},
                ]},
                "Root",
            )

    def test_unknown_parent_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unknown parent"):
            _validate_map(
                {"nodes": [
                    {"id": "root", "parent_id": None, "label": "Root"},
                    {"id": "orphan", "parent_id": "missing", "label": "Orphan"},
                ]},
                "Root",
            )

    def test_fallback_map_is_interactive_graph_data(self):
        result = _fallback_map(
            "Cloud Computing",
            [{"title": "Service Models", "text": "Cloud services include IaaS. PaaS provides a platform. SaaS provides software.", "pages": [2]}],
        )
        self.assertEqual(result["nodes"][0]["label"], "Cloud Computing")
        self.assertTrue(result["edges"])
        self.assertTrue(any(node["source_pages"] == [2] for node in result["nodes"]))


if __name__ == "__main__":
    unittest.main()
