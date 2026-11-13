"""Agentic LangGraph Pipeline for Dynamic Company Interview & Project Research.

Executes a 5-node agentic workflow:
1. discover_and_scrape: Resilient multi-engine web search (GFG, InterviewExperiences, AmbitionBox, PrepInsta, Company Portal).
2. batch_content: Token-safe text chunking respecting LLM context windows.
3. synthesize_company_profile: Executive company profile, tech stack, and flagship client case studies.
4. extract_interview_qna: Extracts real candidate questions and generates expert interview playbooks
   (verbatim STAR responses for behavioral, clarifying questions & production code for technical).
5. consolidate_and_render: Pydantic validation, structured JSON serialization, and publication-grade PDF generation.

STRICT ERROR POLICY:
Fallback mode is disabled. If no valid GROQ_API_KEY or OPENROUTER_API_KEY is configured in .env,
the pipeline raises a RuntimeError and halts immediately.
"""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Optional, TypedDict
from urllib.parse import urlsplit

from dotenv import load_dotenv
from pydantic import BaseModel, Field

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph

from company_search.dynamic_search import run_dynamic_company_research
from company_search.pdf_generator import build_interview_prep_pdf

# Ensure environment variables are loaded
load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = Path(__file__).resolve().parent / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger("agentic_pipeline")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


# ---------------------------------------------------------------------------
# 1. Pydantic Schemas for Strict Data Validation
# ---------------------------------------------------------------------------

class CompanyProject(BaseModel):
    project_name: str = Field(description="Name or title of the engineering system, initiative, or client solution.")
    client_or_industry: str = Field(description="Target client, industry vertical, or internal domain.")
    summary: str = Field(description="Technical summary of the architecture and problem solved.")
    technologies_used: list[str] = Field(default_factory=list, description="Core technologies, frameworks, and tools used.")
    impact: str = Field(default="", description="Quantifiable business or engineering metric / impact.")
    interview_talking_point: str = Field(
        default="",
        description="Exact conversational hook: How a candidate should cite this project to demonstrate company knowledge.",
    )


class CompanyProfile(BaseModel):
    company_name: str
    target_role: str
    overview: str = Field(description="Authoritative executive summary of the company's business model and engineering focus.")
    core_business_domains: list[str] = Field(default_factory=list)
    tech_stack: list[str] = Field(default_factory=list)
    key_projects: list[CompanyProject] = Field(default_factory=list)
    engineering_culture_and_standards: list[str] = Field(
        default_factory=list,
        description="Key engineering values, coding practices, and evaluation tenets expected by the firm.",
    )


class InterviewRound(BaseModel):
    round_number: int
    round_name: str
    round_type: str  # OA, Technical, Managerial, HR
    description: str
    focus_areas: list[str] = Field(default_factory=list)


class QuestionAnswer(BaseModel):
    question: str = Field(description="The exact interview question asked during candidate rounds.")
    category: str = Field(
        default="Technical Coding & DSA",
        description="Category: 'Technical Coding & DSA', 'System Architecture & Design', 'Behavioral & Leadership', 'Domain & Role-Specific'",
    )
    difficulty: str = Field(default="Medium", description="Difficulty level: 'Easy', 'Medium', 'Hard'")
    interviewer_focus: str = Field(
        default="",
        description="What the interviewer is specifically evaluating (core competencies, trade-offs, edge cases, leadership principles).",
    )
    how_to_answer: str = Field(
        default="",
        description="Step-by-step interview strategy: clarifying questions to ask, verbal thought process, and conceptual trade-offs.",
    )
    exemplary_response: str = Field(
        default="",
        description="The definitive high-scoring response. For behavioral: verbatim first-person STAR speech ('This can be said like this: \"...\"'). For technical: optimal implementation with Big-O complexity analysis.",
    )
    traps_to_avoid: str = Field(
        default="",
        description="Specific edge cases, common pitfalls, and red flags that disqualify candidates on this question.",
    )
    source_reference: str = Field(
        default="",
        description="Origin citation (e.g. 'Verified candidate interview report from InterviewExperiences / GeeksforGeeks').",
    )


class InterviewPrepPack(BaseModel):
    metadata: dict[str, Any] = Field(default_factory=dict)
    company_profile: CompanyProfile
    interview_process: list[InterviewRound] = Field(default_factory=list)
    preparation_tips: list[str] = Field(default_factory=list)
    questions_and_answers: list[QuestionAnswer] = Field(default_factory=list)
    sources_consulted: list[dict[str, str]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 2. LLM Provider Factory (Strict Error Policy - No Fallback)
# ---------------------------------------------------------------------------

def get_configured_llm() -> tuple[Any, str]:
    """
    Returns an instantiated LangChain ChatModel and the active provider name.
    Prioritizes GROQ_API_KEY, then OPENROUTER_API_KEY.

    STRICT ERROR POLICY:
    Raises RuntimeError immediately if no valid API key is present. Fallback mode is disabled.
    """
    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    if groq_key and not groq_key.startswith("YOUR_") and not groq_key.startswith("gsk_PLACEHOLDER"):
        try:
            from langchain_groq import ChatGroq
            model_name = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
            logger.info(f"Using Groq LLM: {model_name}")
            return ChatGroq(api_key=groq_key, model_name=model_name, temperature=0.15), "groq"
        except Exception as exc:
            logger.error(f"Failed to initialize ChatGroq: {exc}")
            raise

    openrouter_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if openrouter_key and not openrouter_key.startswith("YOUR_") and not openrouter_key.startswith("sk-or-PLACEHOLDER"):
        # Auto-fix: OpenRouter requires the 'sk-or-v1-' prefix
        if not openrouter_key.startswith("sk-or-"):
            openrouter_key = f"sk-or-v1-{openrouter_key}"
        try:
            from langchain_openai import ChatOpenAI
            model_name = os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free")
            logger.info(f"Using OpenRouter LLM: {model_name}")
            return ChatOpenAI(
                api_key=openrouter_key,
                base_url="https://openrouter.ai/api/v1",
                model=model_name,
                temperature=0.15,
                default_headers={
                    "HTTP-Referer": "https://github.com/placement-prep/fresher-job-scraper",
                    "X-Title": "Professional Placement Interview Dossier Engine",
                },
            ), "openrouter"
        except Exception as exc:
            logger.error(f"Failed to initialize ChatOpenAI (OpenRouter): {exc}")
            raise

    raise RuntimeError(
        "CRITICAL ERROR: No active LLM API key detected!\n"
        "Please configure GROQ_API_KEY or OPENROUTER_API_KEY in your .env file.\n"
        "Deterministic fallback mode has been disabled. Live LLM extraction and expert synthesis are required."
    )


# ---------------------------------------------------------------------------
# 3. Context Batching & Token Chunking Helpers
# ---------------------------------------------------------------------------

def chunk_text_batches(sources: list[dict[str, Any]], max_chars_per_batch: int = 14000) -> list[str]:
    """
    Combines scraped excerpts and texts into token-bounded batches.
    Prevents exceeding LLM context windows.
    """
    batches: list[str] = []
    current_chunk: list[str] = []
    current_len = 0

    for s in sources:
        url = s.get("url", "")
        title = s.get("title", "")
        excerpts = s.get("excerpts", [])
        sample = s.get("full_text_sample", "")

        block = f"\n--- SOURCE: {title} ({url}) ---\n"
        if excerpts:
            block += "Key Excerpts:\n" + "\n".join(f"- {e}" for e in excerpts[:25]) + "\n"
        if sample:
            block += "Sample Content:\n" + sample[:4500] + "\n"

        if current_len + len(block) > max_chars_per_batch and current_chunk:
            batches.append("\n".join(current_chunk))
            current_chunk = [block]
            current_len = len(block)
        else:
            current_chunk.append(block)
            current_len += len(block)

    if current_chunk:
        batches.append("\n".join(current_chunk))

    return batches


def extract_json_object(text: str) -> dict[str, Any]:
    """Robustly extracts a JSON dictionary from LLM output."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()

    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            data = json.loads(text[start : end + 1])
            if isinstance(data, dict):
                return data
        except Exception:
            pass

    raise ValueError(f"Could not parse valid JSON object from LLM response:\n{text[:400]}")


def extract_json_array(text: str) -> list[dict[str, Any]]:
    """Robustly extracts a JSON array of question objects from LLM output."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()

    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ["questions", "questions_and_answers", "qna", "items", "interview_questions"]:
                if key in data and isinstance(data[key], list):
                    return data[key]
    except Exception:
        pass

    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1 and end > start:
        try:
            data = json.loads(text[start : end + 1])
            if isinstance(data, list):
                return data
        except Exception:
            pass

    return []


# ---------------------------------------------------------------------------
# 4. LangGraph State & Node Definitions
# ---------------------------------------------------------------------------

class ResearchState(TypedDict):
    company: str
    role: str
    raw_data: dict[str, Any]
    interview_batches: list[str]
    project_batches: list[str]
    company_profile: dict[str, Any]
    interview_process: list[dict[str, Any]]
    preparation_tips: list[str]
    questions_and_answers: list[dict[str, Any]]
    final_prep_pack: dict[str, Any]
    final_json_path: str
    final_pdf_path: str


def node_discover_and_scrape(state: ResearchState) -> dict[str, Any]:
    """Node 1: Execute dynamic multi-strategy search."""
    company = state["company"]
    role = state["role"]
    logger.info(f"[Node 1/5] Discovering & scraping sources for {company} ({role})...")
    raw = run_dynamic_company_research(company, role, max_interview_sources=4, max_project_sources=3)
    return {"raw_data": raw}


def node_batch_content(state: ResearchState) -> dict[str, Any]:
    """Node 2: Batch scraped text to respect token/context limits."""
    logger.info("[Node 2/5] Batching raw content into token-safe context chunks...")
    raw = state.get("raw_data", {})
    i_sources = raw.get("interview_sources", [])
    p_sources = raw.get("project_sources", [])

    i_batches = chunk_text_batches(i_sources, max_chars_per_batch=12000)
    p_batches = chunk_text_batches(p_sources, max_chars_per_batch=12000)

    logger.info(f"Created {len(i_batches)} interview batches and {len(p_batches)} project batches.")
    return {
        "interview_batches": i_batches,
        "project_batches": p_batches,
    }


def node_synthesize_company_profile(state: ResearchState) -> dict[str, Any]:
    """Node 3: Synthesize company profile & projects via LLM."""
    company = state["company"]
    role = state["role"]
    llm, provider = get_configured_llm()
    p_batches = state.get("project_batches", [])

    if not p_batches:
        # If project search yielded no dedicated pages, use interview batches for context
        p_batches = state.get("interview_batches", [])

    if not p_batches:
        raise RuntimeError(f"No web content scraped for {company}. Cannot synthesize company profile.")

    logger.info(f"[Node 3/5] Synthesizing executive company profile using {provider.upper()}...")
    prompt = f"""You are a Principal Enterprise Solutions Architect and Technology Strategist.
Analyze the following scraped evidence for company '{company}' and target role '{role}'.
Extract an authoritative, executive-grade technology profile and engineering case studies.

RAW SCRAPED EVIDENCE:
{p_batches[0][:12000]}

Return a strict JSON object with this exact structure:
{{
  "company_name": "{company}",
  "target_role": "{role}",
  "overview": "Rigorous executive summary of {company}'s market position, technology ecosystem, and core engineering philosophy...",
  "core_business_domains": ["Domain 1", "Domain 2", "Domain 3"],
  "tech_stack": ["Tech 1", "Tech 2", "Tech 3", ...],
  "key_projects": [
    {{
      "project_name": "Specific flagship initiative / system",
      "client_or_industry": "Client name or industry vertical",
      "summary": "Deep architectural summary of the problem and technical solution deployed",
      "technologies_used": ["Tech A", "Tech B"],
      "impact": "Quantifiable business or engineering metric (e.g. 'Handled 500k RPS with sub-10ms p99 latency')",
      "interview_talking_point": "Exact conversational hook: How an applicant for {role} should cite this project during an interview to demonstrate insider knowledge of {company}'s tech stack"
    }}
  ],
  "engineering_culture_and_standards": [
    "Core engineering tenet 1 (e.g. CI/CD automation, blameless post-mortems)",
    "Core engineering tenet 2",
    "Core engineering tenet 3"
  ]
}}

Respond ONLY with valid JSON. Do not include markdown code block backticks (no ```json)."""

    try:
        res = llm.invoke([
            SystemMessage(content="You are an enterprise technical placement intelligence architect. Return valid JSON only."),
            HumanMessage(content=prompt),
        ])
        profile_data = extract_json_object(res.content)
        return {"company_profile": profile_data}
    except Exception as exc:
        logger.error(f"Failed to synthesize company profile via {provider}: {exc}")
        raise RuntimeError(f"Company profile synthesis failed: {exc}") from exc


def node_extract_interview_qna(state: ResearchState) -> dict[str, Any]:
    """
    Node 4: Discovers candidate interview questions from scraped evidence and generates
    expert-level interview preparation playbooks (verbatim STAR speech for behavioral,
    clarifying questions & production code for technical).
    """
    company = state["company"]
    role = state["role"]
    llm, provider = get_configured_llm()
    i_batches = state.get("interview_batches", [])

    if not i_batches:
        raise RuntimeError(f"No interview evidence scraped for {company} ({role}).")

    logger.info(f"[Node 4/5] Extracting interview questions & generating expert playbooks across {len(i_batches)} batches via {provider.upper()}...")

    all_qna: list[dict[str, Any]] = []

    for b_idx, batch in enumerate(i_batches[:3]):
        prompt = f"""You are a Principal Engineering Director and Senior Hiring Committee Member conducting hiring for '{company}' ({role}).
Analyze the following raw scraped candidate interview experiences, discussions, and transcripts. Produce an elite, publication-grade Interview Preparation Dossier.

RAW SCRAPED EVIDENCE:
{batch[:12000]}

INSTRUCTIONS:
1. DISCOVER QUESTIONS: Figure out all real candidate interview questions, technical problems, coding challenges, behavioral questions, and architectural discussions actually asked in rounds at {company}.
2. BEST POSSIBLE EXPERT ANSWERS (ZERO AI SLOP):
   - For TECHNICAL / CODING / DSA / SQL questions:
     * "interviewer_focus": What core competency, invariant, or scale bottleneck the interviewer is testing.
     * "how_to_answer": Step-by-step interview strategy:
       - 2-3 clarifying questions the candidate MUST ask the interviewer before writing code.
       - The verbal walkthrough explaining naive brute-force intuition and transitioning to the optimal algorithm.
       - Formal Big-O time and auxiliary space complexity proof.
     * "exemplary_response": The complete, production-grade, optimal solution with clean inline comments and edge-case handling.
     * "traps_to_avoid": Specific edge cases, integer overflow, off-by-one errors, or naive mistakes that fail candidates on this question.
   - For BEHAVIORAL / SITUATIONAL / MANAGERIAL / HR questions:
     * "interviewer_focus": The specific leadership competency or company value under evaluation (e.g., Extreme Ownership, Conflict De-escalation with Stakeholders, Customer Empathy).
     * "how_to_answer": The exact STAR framework breakdown (Situation, Task, Action, Result) with timing allocation.
     * "exemplary_response": A realistic, persuasive, word-for-word first-person model response showing how to speak in the room:
       Format: 'This can be said like this: "In my previous project at [Context]... I noticed [Problem]... I personally owned [Action] by executing three steps: 1) ... 2) ... 3) ... As a result, we [Measurable Metric: e.g. reduced latency by 35% / automated 20 hours of manual work]."'
     * "traps_to_avoid": Common behavioral traps (e.g. passive 'we' without personal impact, badmouthing teammates, lacking measurable outcomes).

Return a strict JSON array of objects adhering to this schema:
[
  {{
    "question": "Exact question asked",
    "category": "Technical Coding & DSA | System Architecture & Design | Behavioral & Leadership | Domain & Role-Specific",
    "difficulty": "Easy | Medium | Hard",
    "interviewer_focus": "Specific evaluation criteria...",
    "how_to_answer": "Step-by-step interview navigation, clarifying questions, and verbal strategy...",
    "exemplary_response": "For technical: Optimal commented code or architectural breakdown. For behavioral: 'This can be said like this: \"...\"'",
    "traps_to_avoid": "Specific edge cases, pitfalls, or red flags...",
    "source_reference": "Verified candidate interview report at {company}"
  }}
]

Respond ONLY with a valid JSON array. Do not include markdown code block backticks (no ```json)."""

        try:
            res = llm.invoke([
                SystemMessage(content="You are an elite principal technical interviewer. Return valid JSON array only."),
                HumanMessage(content=prompt),
            ])
            items = extract_json_array(res.content)
            if items:
                all_qna.extend(items)
                logger.info(f"Batch {b_idx + 1}: Extracted {len(items)} high-quality questions.")
        except Exception as exc:
            logger.warning(f"Batch {b_idx + 1} extraction warning: {exc}")

    if not all_qna:
        raise RuntimeError(f"LLM failed to extract candidate questions from scraped content for {company}.")

    # Generate synthesized rounds & strategic prep tips
    rounds = [
        {
            "round_number": 1,
            "round_name": "Online Assessment (OA)",
            "round_type": "Aptitude & Coding",
            "description": f"Timed technical screening covering core algorithms, SQL queries, and role-specific aptitude for {company}.",
            "focus_areas": ["Data Structures & Algorithms", "SQL Aggregations & Joins", "Analytical Reasoning"],
        },
        {
            "round_number": 2,
            "round_name": "Technical Evaluation Round",
            "round_type": "Technical Interview",
            "description": "Deep-dive live coding, system design intuition, algorithmic trade-offs, and resume project defense.",
            "focus_areas": ["Problem-Solving Under Pressure", "Edge Case Rigor", "Code Hygiene & Architecture"],
        },
        {
            "round_number": 3,
            "round_name": "Managerial & Behavioral Fitment",
            "round_type": "Managerial",
            "description": f"Scenario-based problem solving, alignment with {company}'s engineering principles, and teamwork under pressure.",
            "focus_areas": ["STAR Leadership Scenarios", "Cross-Functional Collaboration", "Ambiguity Handling"],
        },
        {
            "round_number": 4,
            "round_name": "HR & Cultural Alignment",
            "round_type": "HR",
            "description": "Long-term career aspirations, cultural fitment, growth mindset, and compensation expectations.",
            "focus_areas": ["Company Alignment", "Ownership Mentality", "Joining Timeline"],
        },
    ]

    tips = [
        f"Master fundamental SQL (Window functions, JOINs, GROUP BY vs HAVING) and core DSA patterns — routinely tested in {company} {role} assessments.",
        "Articulate clarifying questions before writing code or proposing architectures; interviewers grade your problem formulation as heavily as your final solution.",
        f"Ground behavioral answers in the STAR framework with quantified metrics, and prepare conversational hooks linking your skills to {company}'s flagship projects.",
        "Prepare 2-3 thoughtful engineering questions about the team's deployment architecture and onboarding velocity.",
    ]

    return {
        "interview_process": rounds,
        "preparation_tips": tips,
        "questions_and_answers": all_qna,
    }


def node_consolidate_and_render(state: ResearchState) -> dict[str, Any]:
    """Node 5: Validate with Pydantic, save JSON, and generate publication-grade PDF report."""
    company = state["company"]
    role = state["role"]
    logger.info("[Node 5/5] Consolidating data, validating schema, and building publication-grade PDF...")

    clean_comp = re.sub(r"\W+", "_", company.strip().lower())
    clean_role = re.sub(r"\W+", "_", role.strip().lower())

    sources = []
    raw = state.get("raw_data", {})
    for s in raw.get("interview_sources", []) + raw.get("project_sources", []):
        sources.append({
            "domain": (urlsplit(s.get("url", "")).hostname or "").lower(),
            "category": s.get("category", "interview"),
            "url": s.get("url", ""),
        })

    prep_dict = {
        "metadata": {
            "company": company,
            "role": role,
            "total_questions": len(state.get("questions_and_answers", [])),
            "total_sources": len(sources),
        },
        "company_profile": state.get("company_profile", {}),
        "interview_process": state.get("interview_process", []),
        "preparation_tips": state.get("preparation_tips", []),
        "questions_and_answers": state.get("questions_and_answers", []),
        "sources_consulted": sources,
    }

    # Validate against strict Pydantic model
    validated_pack = InterviewPrepPack.model_validate(prep_dict)

    # Save structured JSON
    json_path = RESULTS_DIR / f"{clean_comp}_{clean_role}_prep.json"
    json_path.write_text(validated_pack.model_dump_json(indent=2), encoding="utf-8")
    logger.info(f"Saved verified Q&A JSON to: {json_path}")

    # Generate Publication-Quality PDF
    pdf_path = RESULTS_DIR / f"{clean_comp}_{clean_role}_prep.pdf"
    build_interview_prep_pdf(validated_pack.model_dump(), pdf_path)
    logger.info(f"Generated downloadable PDF report to: {pdf_path}")

    return {
        "final_prep_pack": validated_pack.model_dump(),
        "final_json_path": str(json_path),
        "final_pdf_path": str(pdf_path),
    }


# ---------------------------------------------------------------------------
# 5. Build the LangGraph Execution Workflow
# ---------------------------------------------------------------------------

def build_research_graph() -> Any:
    workflow = StateGraph(ResearchState)

    workflow.add_node("discover_and_scrape", node_discover_and_scrape)
    workflow.add_node("batch_content", node_batch_content)
    workflow.add_node("synthesize_company_profile", node_synthesize_company_profile)
    workflow.add_node("extract_interview_qna", node_extract_interview_qna)
    workflow.add_node("consolidate_and_render", node_consolidate_and_render)

    workflow.add_edge(START, "discover_and_scrape")
    workflow.add_edge("discover_and_scrape", "batch_content")
    workflow.add_edge("batch_content", "synthesize_company_profile")
    workflow.add_edge("synthesize_company_profile", "extract_interview_qna")
    workflow.add_edge("extract_interview_qna", "consolidate_and_render")
    workflow.add_edge("consolidate_and_render", END)

    return workflow.compile()


def run_agentic_research(company: str, role: str) -> dict[str, Any]:
    """
    Main external callable function.
    Executes the entire LangGraph agentic pipeline for any dynamic company & role.
    Raises RuntimeError immediately on millisecond 1 if LLM key is absent.
    """
    # Strict fail-fast: ensure valid LLM credentials before performing any web search
    get_configured_llm()

    app = build_research_graph()
    initial_state: ResearchState = {
        "company": company,
        "role": role,
        "raw_data": {},
        "interview_batches": [],
        "project_batches": [],
        "company_profile": {},
        "interview_process": [],
        "preparation_tips": [],
        "questions_and_answers": [],
        "final_prep_pack": {},
        "final_json_path": "",
        "final_pdf_path": "",
    }
    logger.info(f"Invoking LangGraph research graph for: '{company}' - '{role}'")
    final_state = app.invoke(initial_state)
    return {
        "company": company,
        "role": role,
        "json_path": final_state.get("final_json_path"),
        "pdf_path": final_state.get("final_pdf_path"),
        "total_questions": len(final_state.get("questions_and_answers", [])),
        "total_sources": len(final_state.get("final_prep_pack", {}).get("sources_consulted", [])),
    }
