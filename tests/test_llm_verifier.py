import pytest
from llm_verifier import (
    extract_requirements_and_skills_context,
    verify_fresher_and_curate_skills,
)

def test_extract_requirements_and_skills_context():
    sample = """
    About Our Company
    We are a leading enterprise with 10,000 employees globally.
    Equal Opportunity Employer. All qualified applicants will receive consideration.

    ### Key Responsibilities
    - Build scalable backend microservices.
    - Write clean code in Python and Go.
    - Design and optimize relational databases.

    ### Qualifications and Skills
    - B.Tech or B.E. in Computer Science.
    - Strong understanding of SQL, Git, and Docker.
    - Freshers eligible (0-1 years experience).

    Benefits:
    - Health insurance, 401k, gym membership.
    """
    context = extract_requirements_and_skills_context(sample)
    assert "Build scalable backend microservices" in context
    assert "Python and Go" in context
    assert "SQL, Git, and Docker" in context
    # Boilerplate / EEO stripped
    assert "Equal Opportunity Employer" not in context


def test_verify_fresher_mock_pass():
    class MockLLMPass:
        def invoke(self, messages):
            class Resp:
                content = '{"is_fresher_eligible": true, "experience_detected": "0-1 years", "rejection_reason": null, "curated_skills": "Python, Go, SQL, Docker"}'
            return Resp()

    res = verify_fresher_and_curate_skills(
        "Responsibilities: Build apps. Skills: Python, Go, SQL, Docker. Experience: 0-1 years.",
        title="Software Engineer Trainee",
        company="TechCorp",
        llm=MockLLMPass()
    )
    assert res["is_fresher_eligible"] is True
    assert "Python, Go, SQL, Docker" in res["curated_skills"]


def test_verify_fresher_mock_fail_experienced():
    class MockLLMFail:
        def invoke(self, messages):
            class Resp:
                content = '{"is_fresher_eligible": false, "experience_detected": "3+ years", "rejection_reason": "Requires 3+ years experience in production", "curated_skills": "React, Redux"}'
            return Resp()

    res = verify_fresher_and_curate_skills(
        "Responsibilities: Frontend apps. Requirements: 3+ years experience in production. Skills: React, Redux.",
        title="Web Developer",
        company="TechCorp",
        llm=MockLLMFail()
    )
    assert res["is_fresher_eligible"] is False
    assert "3+ years" in res["rejection_reason"]


def test_rotating_llm_key_failover(monkeypatch):
    from llm_verifier import RotatingLLM
    import os

    monkeypatch.setenv("GROQ_API_KEY1", "key_fail_1")
    monkeypatch.setenv("GROQ_API_KEY2", "key_success_2")
    monkeypatch.delenv("GROQ_API_KEY3", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    call_history = []

    class MockChatOpenAI:
        def __init__(self, api_key, **kwargs):
            self.api_key = api_key

        def invoke(self, messages):
            call_history.append(self.api_key)
            if self.api_key == "key_fail_1":
                raise RuntimeError("429 Rate limit exceeded: tokens per minute limit reached")
            class Resp:
                content = '{"is_fresher_eligible": true, "curated_skills": "Python, SQL"}'
            return Resp()

    monkeypatch.setattr("langchain_openai.ChatOpenAI", MockChatOpenAI)

    rotator = RotatingLLM()
    assert len(rotator.groq_keys) == 2
    res = rotator.invoke("test")
    assert "is_fresher_eligible" in res.content
    # Verified it tried key 1 first, failed on 429, then succeeded on key 2!
    assert call_history == ["key_fail_1", "key_success_2"]
    assert rotator.active_groq_idx == 1

    # Next call should directly use key 2 without repeating key 1!
    rotator.invoke("second call")
    assert call_history == ["key_fail_1", "key_success_2", "key_success_2"]
