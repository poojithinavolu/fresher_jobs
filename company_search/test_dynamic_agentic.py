"""Unit tests for the Agentic Dynamic Company Research & PDF Pipeline."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

# Add project root to sys.path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from company_search.dynamic_search import (
    clean_text,
    get_approved_domains,
    is_host_approved,
    PublicFetcher,
    search_interview_sources,
)
from company_search.agentic_pipeline import (
    chunk_text_batches,
    extract_json_object,
    extract_json_array,
    InterviewPrepPack,
    CompanyProfile,
    CompanyProject,
    QuestionAnswer,
    get_configured_llm,
    node_extract_interview_qna,
)
from company_search.pdf_generator import build_interview_prep_pdf, safe_text


class TestDynamicAgenticPipeline(unittest.TestCase):

    def test_catalog_approved_domains(self):
        domains = get_approved_domains("interview")
        self.assertIn("geeksforgeeks.org", domains)
        self.assertIn("interviewexperiences.in", domains)
        self.assertTrue(is_host_approved("https://www.geeksforgeeks.org/some-article", "interview"))
        self.assertTrue(is_host_approved("https://interviewexperiences.in/company/google", "interview"))
        self.assertFalse(is_host_approved("https://malicious-site.com/hack", "interview"))

    def test_chunk_text_batches(self):
        sample_sources = [
            {"title": "Doc 1", "url": "https://a.com", "excerpts": ["Excerpt A" * 100], "full_text_sample": "Sample text " * 200},
            {"title": "Doc 2", "url": "https://b.com", "excerpts": ["Excerpt B" * 100], "full_text_sample": "Sample text " * 200},
        ]
        batches = chunk_text_batches(sample_sources, max_chars_per_batch=1000)
        self.assertGreaterEqual(len(batches), 2)
        self.assertIn("Doc 1", batches[0])

    def test_strict_key_error_policy(self):
        """Verify that missing API keys strictly raise a RuntimeError instead of silent fallback."""
        cleared_keys = {
            "GROQ_API_KEY": "", "GROQ_API_KEY1": "", "GROQ_API_KEY2": "", "GROQ_API_KEY3": "",
            "GROQ_API_KEY_1": "", "GROQ_API_KEY_2": "", "GROQ_API_KEY_3": "",
            "OPENROUTER_API_KEY": "", "OPENROUTER_API_KEY1": "", "OPENROUTER_API_KEY2": "", "OPENROUTER_API_KEY3": "",
            "OPENROUTER_API_KEY_1": "", "OPENROUTER_API_KEY_2": "", "OPENROUTER_API_KEY_3": "",
        }
        with patch.dict(os.environ, cleared_keys):
            with self.assertRaises(RuntimeError) as ctx:
                get_configured_llm()
            self.assertIn("CRITICAL ERROR: No active LLM API key detected", str(ctx.exception))

    def test_extract_json_helpers(self):
        # Test markdown code block stripping
        raw_obj = '```json\n{"company_name": "Acme", "overview": "Test"}\n```'
        parsed_obj = extract_json_object(raw_obj)
        self.assertEqual(parsed_obj["company_name"], "Acme")

        raw_arr = '```json\n[{"question": "What is SQL?", "category": "Technical"}]\n```'
        parsed_arr = extract_json_array(raw_arr)
        self.assertEqual(len(parsed_arr), 1)
        self.assertEqual(parsed_arr[0]["question"], "What is SQL?")

    def test_malformed_llm_json_is_retried_with_diagnostic_safe_parser(self):
        class Response:
            def __init__(self, content, metadata=None):
                self.content = content
                self.response_metadata = metadata or {}

        class FakeLLM:
            def __init__(self):
                self.calls = 0

            def invoke(self, _messages):
                self.calls += 1
                if self.calls == 1:
                    return Response('{"questions": [{"question": "truncated"', {"finish_reason": "length", "token_usage": {"completion_tokens": 100}})
                return Response('{"questions": [{"question": "Explain a SQL join", "category": "Technical", "difficulty": "Easy"}]}')

        fake = FakeLLM()
        state = {"company": "Cognizant", "role": "Analyst", "interview_batches": ["Candidate report: Explain a SQL join."]}
        with patch("company_search.agentic_pipeline.get_configured_llm", return_value=(fake, "groq")), patch("company_search.agentic_pipeline.time.sleep"):
            result = node_extract_interview_qna(state)
        self.assertEqual(fake.calls, 2)
        self.assertEqual(result["questions_and_answers"][0]["question"], "Explain a SQL join")

    def test_valid_empty_llm_result_is_not_replaced_with_invented_questions(self):
        class Response:
            content = '{"questions": []}'
            response_metadata = {"finish_reason": "stop"}

        class FakeLLM:
            calls = 0

            def invoke(self, _messages):
                self.calls += 1
                return Response()

        fake = FakeLLM()
        state = {"company": "Cognizant", "role": "Analyst", "interview_batches": ["Candidate report only mentions two interview rounds."]}
        with patch("company_search.agentic_pipeline.get_configured_llm", return_value=(fake, "groq")), patch("company_search.agentic_pipeline.time.sleep"):
            with self.assertRaisesRegex(RuntimeError, "valid JSON contained no source-backed questions"):
                node_extract_interview_qna(state)
        self.assertEqual(fake.calls, 1)

    def test_interview_search_rejects_unapproved_domains(self):
        fake_result = {"title": "Cognizant interview", "url": "https://random.example/interview", "snippet": "questions"}
        with patch("company_search.dynamic_search.execute_ddgs_search", return_value=[fake_result]), patch("company_search.dynamic_search.time.sleep"):
            hits = search_interview_sources("Cognizant", "Analyst", max_sources=3)
        self.assertEqual(hits, [])

    def test_pydantic_schema_and_pdf_generation(self):
        """Tests full validation of professional schema and publication-grade PDF generation."""
        profile = {
            "company_name": "Google",
            "target_role": "SDE1",
            "overview": "Google builds global-scale search, cloud infrastructure, and AI systems powering billions of daily transactions.",
            "core_business_domains": ["Search & Information", "Cloud Platforms", "Advertising Technology"],
            "tech_stack": ["C++", "Java", "Python", "Go", "Spanner", "Kubernetes", "BigQuery"],
            "key_projects": [
                {
                    "project_name": "Spanner Globally-Distributed Database",
                    "client_or_industry": "Google Cloud & Enterprise",
                    "summary": "Synchronously-replicated global database providing external consistency with atomic clocks.",
                    "technologies_used": ["C++", "TrueTime API", "Paxos"],
                    "impact": "Achieved 99.999% SLA across multi-region enterprise clusters.",
                    "interview_talking_point": "Reference TrueTime API and Paxos consensus when answering distributed systems questions.",
                }
            ],
            "engineering_culture_and_standards": [
                "Strict peer code review with readability guidelines",
                "Blameless post-mortem culture for system outages",
                "Automated end-to-end testing with 90%+ branch coverage",
            ],
        }

        qna = [
            {
                "question": "Implement Multiple Timers on a Single Hardware Timer",
                "category": "Technical Coding & DSA",
                "difficulty": "Hard",
                "interviewer_focus": "Tests event-driven systems programming, priority queues, and hardware-software interrupt trade-offs.",
                "how_to_answer": "1. Clarify time resolution (milliseconds vs microseconds) and whether timers are one-shot or periodic.\n2. Explain naive O(n) polling vs optimal O(log n) min-heap or O(1) hashed timer wheel.\n3. Detail how to reprogram the single hardware comparator on timer expiration.",
                "exemplary_response": "def schedule_timer(delay_ms, callback):\n    # Optimal solution using min-heap priority queue\n    heapq.heappush(timers, (current_time + delay_ms, callback))\n    reprogram_hardware_timer(timers[0][0] - current_time)",
                "traps_to_avoid": "Failing to account for timer drift during interrupt handling, or neglecting thread safety during cancellation.",
                "source_reference": "Verified candidate interview report at Google (L3/SDE1 onsite round)",
            },
            {
                "question": "Tell me about a time you had a fundamental disagreement with a technical lead or teammate.",
                "category": "Behavioral & Leadership",
                "difficulty": "Medium",
                "interviewer_focus": "Evaluates mature disagreement de-escalation, data-driven persuasion, and blameless commitment to team goals.",
                "how_to_answer": "Structure strictly using STAR. Spend 10% on the disagreement, 15% on the technical trade-off, 60% on collaborative testing/data gathering, and 15% on the outcome and relationship preservation.",
                "exemplary_response": 'This can be said like this: "In my previous project at University Labs, our tech lead wanted to use MongoDB for transaction logs while I favored PostgreSQL for strict ACID constraints. Rather than debating theoretically, I spent one afternoon benchmarking both databases under a simulated 10k concurrent write load. The benchmarks demonstrated that PostgreSQL prevented 4% data corruption that occurred in Mongo during simulated crash recovery. When I presented the telemetry respectfully, the lead agreed to adopt Postgres, and our deployment ran with zero transaction errors throughout the entire release."',
                "traps_to_avoid": "Never badmouth the tech lead or frame the interaction as winning an argument; emphasize empirical data and collective delivery.",
                "source_reference": "Googleyness & Leadership behavioral round transcript",
            },
        ]

        pack_data = {
            "metadata": {"company": "Google", "role": "SDE1", "total_questions": len(qna), "total_sources": 1},
            "company_profile": profile,
            "interview_process": [
                {"round_number": 1, "round_name": "Online Assessment (OA)", "round_type": "OA", "description": "HackerRank 2 DSA problems", "focus_areas": ["Graphs", "DP"]}
            ],
            "preparation_tips": [
                "Focus on graph algorithms, Dijkstra with early termination, and streaming heaps.",
                "Always write clean modular code and articulate assumptions before typing.",
            ],
            "questions_and_answers": qna,
            "sources_consulted": [{"domain": "geeksforgeeks.org", "category": "interview", "url": "https://geeksforgeeks.org/google-interview-prep"}],
        }

        # Validate with strict Pydantic model
        validated = InterviewPrepPack.model_validate(pack_data)
        self.assertEqual(validated.company_profile.company_name, "Google")
        self.assertEqual(len(validated.questions_and_answers), 2)
        self.assertIn("This can be said like this", validated.questions_and_answers[1].exemplary_response)

        # Test PDF generation
        out_pdf = ROOT / "company_search" / "results" / "unit_test_dossier.pdf"
        pdf_path = build_interview_prep_pdf(validated.model_dump(), out_pdf)
        self.assertTrue(os.path.exists(pdf_path))
        self.assertGreater(os.path.getsize(pdf_path), 5000)


if __name__ == "__main__":
    unittest.main()
