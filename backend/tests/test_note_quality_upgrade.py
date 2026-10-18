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

    def test_semantic_chunks_keep_source_page_and_heading_metadata(self):
        from services.chunking_service import chunk_document

        source = (
            "[[PAGE_1]]\nCloud Computing\n"
            + ("Cloud computing provides on-demand network access to shared configurable resources. " * 12)
            + "\n\n[[PAGE_2]]\nDeployment Models\n"
            + ("Deployment models define where cloud resources are hosted and managed. " * 12)
        )
        chunks = chunk_document(source, "quality-test.pdf", chunk_size=500, overlap=80)
        self.assertTrue(chunks)
        self.assertTrue(all(chunk.get("document_id") for chunk in chunks))
        self.assertTrue(all(chunk.get("source_pages") for chunk in chunks))
        self.assertTrue(all(chunk.get("page") in {1, 2} for chunk in chunks))
        self.assertTrue(any("Cloud Computing" in str(chunk.get("heading") or "") for chunk in chunks))

    def test_targeted_note_generation_exposes_real_fallback_status(self):
        from unittest.mock import patch
        from services.targeted_note_generation import generate_targeted_note_package

        pipeline_result = {
            "sections": [{
                "section_id": "section-1",
                "title": "Cloud deployment",
                "content": "Cloud deployment models describe where cloud infrastructure is hosted.",
                "raw_text": "Cloud deployment models describe where cloud infrastructure is hosted.",
                "generation_status": "fallback",
                "generation_metadata": {"status": "fallback", "reason": "invalid_structured_output"},
                "key_points": ["Deployment models determine where cloud infrastructure is hosted."],
                "definitions": [],
                "examples": [],
                "use_cases": [],
                "important_notes": [],
                "common_mistakes": [],
                "revision_notes": [],
                "memory_tricks": [],
                "concept_comparisons": [],
                "test_yourself": [],
                "diagrams": [],
                "page_numbers": [2],
            }],
            "questions": [],
            "document_intelligence": {"document_summary": "Source-based summary"},
            "retrieval": {"pages": [2]},
        }
        with patch("services.targeted_note_generation.run_targeted_note_pipeline", return_value=pipeline_result):
            package = generate_targeted_note_package(
                context="Cloud deployment models describe where cloud infrastructure is hosted.",
                topic="Cloud deployment",
                source_metadata={"filename": "cloud.pdf", "pages": [2]},
            )
        self.assertEqual(package["generation_mode"], "targeted")
        self.assertEqual(package["generation_metadata"]["mode"], "fallback")
        self.assertEqual(package["generation_metadata"]["sections_fallback"], 1)


if __name__ == "__main__":
    unittest.main()
