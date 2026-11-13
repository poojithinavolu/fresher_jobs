# Professional Agentic Company Interview Research & Dossier Generation Pipeline

An enterprise-grade, multi-source intelligence system built with **LangGraph**, **LangChain**, and **ReportLab**. It operates **on-the-spot for ANY company and role**, dynamically discovers candidate interview experiences and company engineering case studies, batches content to respect LLM context limits, extracts verified candidate questions, formulates expert-level interview playbooks (verbatim STAR responses for behavioral, clarifying questions & production code for technical), and renders a publication-quality downloadable PDF.

---

## Architecture Overview

```
[Target: Company & Role]
           │
           ▼
[1. Dynamic Multi-Source Search (dynamic_search.py)]
   ├─ Interview Sources: InterviewExperiences.in, GeeksforGeeks, AmbitionBox, PrepInsta, Board Infinity
   ├─ Engineering Sources: Flagship client case studies, architecture briefs, tech stack disclosures
   └─ Polite robots.txt & safe redirect enforcement (PublicFetcher via httpx)
           │
           ▼
[2. Context Batching & Token Chunking (agentic_pipeline.py)]
   └─ Token-bounded batching (prevents exceeding LLM context windows)
           │
           ▼
[3. Agentic LLM Synthesis (LangGraph StateGraph)]
   ├─ Multi-provider support via .env (Groq or OpenRouter)
   ├─ Strict Error Policy: Live LLM key required; halts immediately if key is missing (Zero fallback slop)
   ├─ Executive Company Profile & Flagship Case Studies extraction
   └─ Curated Q&A Formulation:
       • Technical / Coding: Clarifying questions, verbal walkthrough, optimal code, Big-O proof, edge-case traps
       • Behavioral / Leadership: Verbatim first-person STAR model answers ('This can be said like this: "..."')
           │
           ▼
[4. Schema Validation & Data Packaging]
   └─ Validated against Pydantic InterviewPrepPack schema -> Saves <company>_<role>_prep.json
           │
           ▼
[5. Publication-Grade PDF Generation (pdf_generator.py)]
   └─ ReportLab Platypus engine with NumberedCanvas ("Page X of Y"), difficulty badges,
      interviewer evaluation criteria, verbal walkthrough playbooks, and trap callouts
      -> Saves downloadable <company>_<role>_prep.pdf
```

---

## Quickstart & CLI Commands

### 1. Research Any Company and Role On-The-Spot:
```powershell
# Run for any arbitrary company & role dynamically:
python company_search/run_research.py --company "Google" --role "SDE1"
python company_search/run_research.py --company "Hitachi" --role "Data Analyst"
python company_search/run_research.py --company "TCS" --role "Web Developer"
python company_search/run_research.py --company "indē wild" --role "Junior Data Analyst"
```

### 2. Research Top Jobs Directly from Scraper Output:
```powershell
python company_search/run_research.py --from-scraper --max-jobs 2
```

### 3. Run Unit Tests:
```powershell
python company_search/test_dynamic_agentic.py
```

---

## Configuring LLM Providers (Groq / OpenRouter)

In your root `.env` file, configure your preferred provider. An active API key is **strictly required**:

### Option A: OpenRouter (Top Free Flagship Models)
```env
OPENROUTER_API_KEY=sk-or-v1-your_openrouter_key_here
OPENROUTER_MODEL=nvidia/nemotron-3-ultra-550b-a55b:free
# Alternate options:
# OPENROUTER_MODEL=openrouter/free
# OPENROUTER_MODEL=meta-llama/llama-3.3-70b-instruct:free
```

### Option B: Groq (Blazing Fast LPUs, 131k Context, 100% Free Tier)
```env
GROQ_API_KEY=gsk_your_groq_api_key_here
GROQ_MODEL=openai/gpt-oss-120b
# Alternate option:
# GROQ_MODEL=llama-3.3-70b-versatile
```

> **Strict Error Policy:** If neither key is present, the pipeline raises a `RuntimeError` immediately and halts. There is no synthetic heuristic fallback.

---

## Outputs Generated

For every researched company, the pipeline saves two synchronized artifacts in `company_search/results/`:

1. **Structured JSON Pack** (`<company>_<role>_prep.json`):
   - Executive Company Profile, Core Business Domains, and Primary Tech Stack
   - Flagship Client Projects with Technologies Used, Impact Metrics, and Interview Talking Points
   - Candidate Evaluation Pipeline (Rounds 1–4) & Strategic Preparation Playbook
   - Curated Q&As adhering to the upgraded schema:
     - `question`: Exact candidate question asked
     - `category`: Technical Coding & DSA | System Architecture | Behavioral & Leadership | Domain
     - `difficulty`: Easy | Medium | Hard
     - `interviewer_focus`: Core competencies and trade-offs under evaluation
     - `how_to_answer`: Clarifying questions, verbal structuring, and conceptual walkthrough
     - `exemplary_response`: Verbatim first-person STAR speech or optimal commented code
     - `traps_to_avoid`: Critical edge cases, common pitfalls, and disqualifying red flags
     - `source_reference`: Candidate experience origin
   - Evidence Sources Ledger
2. **Downloadable PDF Dossier** (`<company>_<role>_prep.pdf`):
   - Publication-grade typography and executive layout
   - Dynamic header and footer ("Page X of Y")
   - Color-coded difficulty badges (Green: Easy, Amber: Medium, Red: Hard)
   - Distinctive containers for verbatim behavioral delivery, code solutions, and red flag traps
