import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import services.mind_map_service as mind_map_service
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

    def test_saved_map_is_reused_without_regeneration(self):
        note = {
            "id": "note-1",
            "title": "Cloud Computing",
            "topic": "Cloud Computing",
            "source": "generated",
            "package": {
                "document_title": "Cloud Computing",
                "sections": [
                    {"title": "Service Models", "content": "IaaS provides infrastructure. PaaS provides a platform.", "page_numbers": [2]}
                ],
            },
        }
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(mind_map_service, "DATA_DIR", Path(temporary)), \
                 patch.object(mind_map_service, "STORE_PATH", Path(temporary) / "mind_maps.json"), \
                 patch.object(mind_map_service, "get_note_record", return_value=note), \
                 patch.object(mind_map_service, "has_llm_support", return_value=False), \
                 patch.object(mind_map_service, "_generate", wraps=mind_map_service._generate) as generate:
                first = mind_map_service.generate_mind_map("note-1")
                second = mind_map_service.generate_mind_map("note-1")
                self.assertEqual(first, second)
                self.assertEqual(generate.call_count, 1)

    def test_failed_regeneration_preserves_saved_map(self):
        note = {
            "id": "note-1",
            "title": "Cloud Computing",
            "topic": "Cloud Computing",
            "source": "generated",
            "package": {
                "document_title": "Cloud Computing",
                "sections": [{"title": "Service Models", "content": "IaaS provides infrastructure.", "page_numbers": [2]}],
            },
        }
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(mind_map_service, "DATA_DIR", Path(temporary)), \
                 patch.object(mind_map_service, "STORE_PATH", Path(temporary) / "mind_maps.json"), \
                 patch.object(mind_map_service, "get_note_record", return_value=note), \
                 patch.object(mind_map_service, "has_llm_support", return_value=False):
                saved = mind_map_service.generate_mind_map("note-1")
                with patch.object(mind_map_service, "_generate", side_effect=RuntimeError("provider failed")):
                    with self.assertRaisesRegex(RuntimeError, "provider failed"):
                        mind_map_service.generate_mind_map("note-1", force=True)
                self.assertEqual(mind_map_service.get_saved_mind_map("note-1"), saved)

    def test_fallback_map_is_interactive_graph_data(self):
        result = _fallback_map(
            "Cloud Computing",
            [{"title": "Service Models", "text": "Cloud services include IaaS. PaaS provides a platform. SaaS provides software.", "pages": [2]}],
        )
        self.assertEqual(result["nodes"][0]["label"], "Cloud Computing")
        self.assertTrue(result["edges"])
        self.assertTrue(any(node["source_pages"] == [2] for node in result["nodes"]))

    def test_topic_maps_are_cached_separately(self):
        note = {
            "id": "note-1",
            "title": "Cloud Computing",
            "topic": "Cloud Computing",
            "source": "generated",
            "package": {
                "document_title": "Cloud Computing",
                "sections": [
                    {"title": "Service Models", "content": "IaaS provides infrastructure. PaaS provides a platform.", "page_numbers": [2]},
                    {"title": "Deployment Models", "content": "Public cloud serves many users. Private cloud serves one organization.", "page_numbers": [4]},
                ],
            },
        }
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(mind_map_service, "DATA_DIR", Path(temporary)), \\
                 patch.object(mind_map_service, "STORE_PATH", Path(temporary) / "mind_maps.json"), \\
                 patch.object(mind_map_service, "get_note_record", return_value=note), \\
                 patch.object(mind_map_service, "has_llm_support", return_value=False):
                services = mind_map_service.generate_mind_map("note-1", "Service Models")
                deployment = mind_map_service.generate_mind_map("note-1", "Deployment Models")
                self.assertNotEqual(services["source_version"], deployment["source_version"])
                self.assertEqual(mind_map_service.get_saved_mind_map("note-1", "Service Models"), services)
                self.assertEqual(mind_map_service.get_saved_mind_map("note-1", "Deployment Models"), deployment)

    def test_invalid_llm_graph_uses_deterministic_fallback(self):
        note = {
            "id": "note-1",
            "title": "Cloud Computing",
            "topic": "Cloud Computing",
            "source": "generated",
            "package": {
                "document_title": "Cloud Computing",
                "sections": [{"title": "Service Models", "content": "IaaS provides infrastructure. PaaS provides a platform.", "page_numbers": [2]}],
            },
        }
        with patch.object(mind_map_service, "get_note_record", return_value=note), \\
             patch.object(mind_map_service, "has_llm_support", return_value=True), \\
             patch.object(mind_map_service, "generate_structured_json", return_value={"nodes": [{"id": "root", "parent_id": None}, {"id": "orphan", "parent_id": "missing"}], "edges": []}):
            result = mind_map_service._generate(note, "note-1", None)
        self.assertEqual(result["generation_method"], "deterministic_fallback")
        self.assertEqual(result["nodes"][0]["label"], "Cloud Computing")
        self.assertTrue(result["edges"])


if __name__ == "__main__":
    unittest.main()
