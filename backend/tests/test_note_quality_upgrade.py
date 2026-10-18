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

    def test_validator_detects_suspicious_truncated_prose(self):
        from services.note_quality_validator import _has_suspicious_truncated_ending

        self.assertTrue(_has_suspicious_truncated_ending("The deployment depends on the availability of..."))
        self.assertTrue(_has_suspicious_truncated_ending("The service provides access to"))
        self.assertFalse(_has_suspicious_truncated_ending("Cloud services scale with demand."))

    def test_semantic_chunks_keep_source_page_and_heading_metadata(self):
        from services.chunking_service import chunk_document

        source = (
            "[[PAGE_1]]\nCHAPTER 1: CLOUD COMPUTING\n"
            + ("Cloud computing provides on-demand network access to shared configurable resources. " * 12)
            + "\n\n[[PAGE_2]]\nCHAPTER 2: DEPLOYMENT MODELS\n"
            + ("Deployment models define where cloud resources are hosted and managed. " * 12)
        )
        chunks = chunk_document(source, "quality-test.pdf", chunk_size=500, overlap=80)
        self.assertTrue(chunks)
        self.assertTrue(all(chunk.get("document_id") for chunk in chunks))
        self.assertTrue(all(chunk.get("source_pages") for chunk in chunks))
        self.assertTrue(all(chunk.get("page") in {1, 2} for chunk in chunks))
        self.assertTrue(any("CHAPTER 1" in str(chunk.get("heading") or "") for chunk in chunks))

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


    def test_targeted_retrieval_excludes_chunks_without_topic_evidence(self):
        from unittest.mock import patch
        from services.targeted_retrieval_service import retrieve_targeted_chunks

        matches = [
            {
                "chunk_id": "components-page-2",
                "document_id": "doc-1",
                "filename": "cloud.pdf",
                "page": 2,
                "chunk_index": 2,
                "page_chunk_index": 0,
                "heading": "Components of Cloud Computing",
                "text": "Components of cloud computing include client devices, datacentres, distributed servers, front-end and back-end platforms, and the delivery network.",
                "score": 0.64,
            },
            {
                "chunk_id": "api-page-6",
                "document_id": "doc-1",
                "filename": "cloud.pdf",
                "page": 6,
                "chunk_index": 12,
                "page_chunk_index": 0,
                "heading": "Cloud APIs",
                "text": "Cloud APIs let applications provision virtual machines and integrate services programmatically.",
                "score": 0.91,
            },
            {
                "chunk_id": "deployment-page-6",
                "document_id": "doc-1",
                "filename": "cloud.pdf",
                "page": 6,
                "chunk_index": 13,
                "page_chunk_index": 1,
                "heading": "Cloud Deployment Models",
                "text": "Public, private, hybrid, and community cloud models vary in ownership and control.",
                "score": 0.83,
            },
        ]

        with patch("services.targeted_retrieval_service.embed_query", return_value=[0.1] * 384), patch(
            "services.targeted_retrieval_service.search_chunks", return_value=matches
        ):
            result = retrieve_targeted_chunks(
                document_id="doc-1",
                query="Components of Cloud Computing",
                top_k=5,
                max_chunks=10,
            )

        self.assertEqual(result["document_id"], "doc-1")
        self.assertEqual(result["pages"], [2])
        self.assertEqual(len(result["matches"]), 1)
        self.assertEqual(result["matches"][0]["heading"], "Components of Cloud Computing")
        self.assertIn("client devices", result["source_text"])
        self.assertNotIn("Cloud APIs let applications", result["source_text"])

    def test_targeted_retrieval_removes_identical_chunk_text(self):
        from services.targeted_retrieval_service import _deduplicate_by_text

        matches = [
            {"chunk_id": "a", "score": 0.6, "text": "Components include clients, datacentres, and distributed servers."},
            {"chunk_id": "b", "score": 0.8, "text": "Components include clients, datacentres, and distributed servers."},
        ]
        result = _deduplicate_by_text(matches)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["chunk_id"], "b")

    def test_targeted_retrieval_lexical_match_uses_word_boundaries(self):
        from services.targeted_retrieval_service import _lexical_relevance

        exact = {
            "heading": "Components of Cloud Computing",
            "text": "Components include client devices and datacentres.",
        }
        partial = {
            "heading": "Cloud APIs",
            "text": "This API exposes cloud service components through a console.",
        }
        self.assertGreater(_lexical_relevance("Components of Cloud Computing", exact), 0)
        self.assertEqual(_lexical_relevance("Components of Cloud Computing", {"heading": "Cloud APIs", "text": "API calls provision services."}), 0)


if __name__ == "__main__":
    unittest.main()
