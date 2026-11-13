# Next-Agent Handoff: Fresher Job Scraper and Agentic Company Interview Research

**Updated:** 13 November 2026  
**Repository:** `D:\freelance\case study\fresher_job_scraper`  
**Purpose:** Executive documentation and technical handoff for the full end-to-end fresher job scraper and agentic company interview research dossier engine.

---

## 1. System Architecture Overview

The system consists of two major decoupled components:
1. **Fresher Job Scraper & Board Automation (`scraper.py`, `filter_engine.py`, `google_sheets_sync.py`, `main.py`)**:
   - Collects real-time fresher listings from JobSpy (Naukri, Indeed, LinkedIn).
   - Filters out non-fresher listings (experience ceilings, irrelevant keywords, blacklist).
   - Syncs verified jobs to Google Sheets with deduplication.
2. **Agentic Company Interview Dossier Engine (`company_search/`)**:
   - **Dynamic Web Search (`dynamic_search.py`)**: Multi-source discovery across approved candidate platforms (GeeksforGeeks, InterviewExperiences.in, AmbitionBox, PrepInsta, Board Infinity) and corporate project case studies.
   - **Context Batching & Token Chunking (`agentic_pipeline.py`)**: Bounded batching respecting LLM context windows.
   - **Strict Fail-Fast Error Policy**: Raises `RuntimeError` on millisecond 1 if no valid `GROQ_API_KEY` or `OPENROUTER_API_KEY` is present. Deterministic fallback mode has been completely removed per system specification.
   - **LangGraph Agentic Workflow**:
     - *Node 1: discover_and_scrape* (Polite, resilient web crawling)
     - *Node 2: batch_content* (Token-bounded batching)
     - *Node 3: synthesize_company_profile* (Corporate architecture, tech stack, flagship client case studies, engineering standards)
     - *Node 4: extract_interview_qna* (Extracts real questions, formulates expert answers: verbatim STAR delivery for behavioral, clarifying questions & production code for technical)
     - *Node 5: consolidate_and_render* (Pydantic validation, structured JSON serialization, and publication-grade PDF generation)
   - **Publication-Grade PDF Generator (`pdf_generator.py`)**:
     - ReportLab Platypus engine with custom `NumberedCanvas` ("Page X of Y" and running headers)
     - Color-coded difficulty badges (Green: Easy, Amber: Medium, Red: Hard)
     - Dedicated containers for verbatim behavioral delivery, technical code implementations, and red-flag traps.

---

## 2. Upgraded Schema Specification

The pipeline uses strict Pydantic models in `company_search/agentic_pipeline.py`:

```python
class QuestionAnswer(BaseModel):
    question: str
    category: str  # Technical Coding & DSA | System Architecture & Design | Behavioral & Leadership | Domain & Role-Specific
    difficulty: str  # Easy | Medium | Hard
    interviewer_focus: str  # Core competencies, edge cases, trade-offs under evaluation
    how_to_answer: str  # Step-by-step interview strategy & verbal navigation
    exemplary_response: str  # Verbatim first-person STAR speech or optimal commented code
    traps_to_avoid: str  # Disqualifying edge cases, naive bugs, and behavioral red flags
    source_reference: str  # Candidate experience origin
```

---

## 3. Supported CLI Commands

```powershell
# Run dynamic research for any company and role:
python company_search/run_research.py --company "Google" --role "SDE1"
python company_search/run_research.py --company "Hitachi" --role "Data Analyst"
python company_search/run_research.py --company "TCS" --role "Web Developer"

# Process directly from latest scraped jobs:
python company_search/run_research.py --from-scraper --max-jobs 2

# Execute unit test suite (5/5 passing):
python company_search/test_dynamic_agentic.py
```

---

## 4. Key Configuration

Configured in [.env](file:///d:/freelance/case%20study/fresher_job_scraper/.env):
- `OPENROUTER_API_KEY`: Auto-validates `sk-or-v1-` prefix.
- `OPENROUTER_MODEL`: Recommended free tier: `nvidia/nemotron-3-ultra-550b-a55b:free`, `openrouter/free`, `meta-llama/llama-3.3-70b-instruct:free`.
- `GROQ_API_KEY`: Groq LPU execution.
- `GROQ_MODEL`: Recommended free tier: `openai/gpt-oss-120b`, `llama-3.3-70b-versatile`.
