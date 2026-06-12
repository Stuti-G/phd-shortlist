# PhD Shortlist Builder

An automated, end-to-end system that ingests a student's profile (including education history, research interests, projects, and target countries) and produces a ranked, verified, and personalized shortlist of PhD **supervisors** (PIs) and linked programs. 

The core system architecture is built around a single, guiding principle: **contamination is penalized heavier than coverage.** The pipeline operates as a strict, multi-stage "funnel of filters" that defaults to a fail-closed status at every gate.

---

## How It Works

```
                     student.json
                          │
                          ▼
    ┌──────────────────────────────────────────┐
    │  [1] parse_profile (LLM keywords)        │
    └─────────────────────┬────────────────────┘
                          ▼
    ┌──────────────────────────────────────────┐
    │  [2] retrieve (OpenAlex Search /works)   │  ◄── Hard Target Country Constraint
    └─────────────────────┬────────────────────┘
                          ▼
    ┌──────────────────────────────────────────┐
    │  [3] resolve_pis (Heuristics Filter)    │  ◄── Career-Stage Guard (FM 6.2)
    └─────────────────────┬────────────────────┘
                          ▼
    ┌──────────────────────────────────────────┐
    │  [4] disambiguate (Cosine Similarity)    │  ◄── Name Collision Guard (FM 6.1)
    └─────────────────────┬────────────────────┘
                          ▼
    ┌──────────────────────────────────────────┐
    │  [5] domain_gate (LLM Discipline Check)  │  ◄── Keyword Overlap Guard (FM 6.3)
    └─────────────────────┬────────────────────┘
                          ▼
    ┌──────────────────────────────────────────┐
    │  [6] build_evidence (Paper/Grant Match)  │  ◄── Fellowship/Integrity Check (FM 6.2)
    └─────────────────────┬────────────────────┘
                          ▼
    ┌──────────────────────────────────────────┐
    │  [7] eligibility (LLM Residency Check)   │  ◄── Visa/Funding Guard (FM 6.4)
    └─────────────────────┬────────────────────┘
                          ▼
    ┌──────────────────────────────────────────┐
    │  [8] rank_tier (Multi-dimensional Score) │  ◄── Bayesian Feedback Priors Nudge
    └─────────────────────┬────────────────────┘
                          ▼
    ┌──────────────────────────────────────────┐
    │  [9] why_match (Personalized Hook)       │  ◄── Specific work citations
    └─────────────────────┬────────────────────┘
                          │
                          ▼
                    shortlist.json
```

---

## Pipeline Stages & Failure Mode Resolution

1. **[parse_profile](file:///C:/Users/stuti/Downloads/phd-shortlist%20(1)/phd-shortlist/shortlist/stages/parse_profile.py)**: Parses stated student interests into concise, academic search queries using an LLM.
2. **[retrieve](file:///C:/Users/stuti/Downloads/phd-shortlist%20(1)/phd-shortlist/shortlist/stages/retrieve.py)**: Queries OpenAlex for publications related to parsed search terms, enforcing target country constraints at the affiliation level.
3. **[resolve_pis](file:///C:/Users/stuti/Downloads/phd-shortlist%20(1)/phd-shortlist/shortlist/stages/resolve_pis.py)**: Excludes junior researchers and non-PIs. Uses a **last-author heuristic**, a career span threshold ($\ge 4$ years), and total works count ($\ge 8$). *(Resolves FM 6.2)*
4. **[disambiguation_ok](file:///C:/Users/stuti/Downloads/phd-shortlist%20(1)/phd-shortlist/shortlist/stages/domain_gate.py)**: Resolves name collisions using OpenAlex Author IDs instead of name strings, checking candidate topic profiles against the student's area using MiniLM-L6-v2 embeddings. *(Resolves FM 6.1)*
5. **[domain_gate](file:///C:/Users/stuti/Downloads/phd-shortlist%20(1)/phd-shortlist/shortlist/stages/domain_gate.py)**: Passes candidate works to a structured LLM audit. The gate is primed with cross-discipline traps (e.g., Roman trauma vs. clinical PTSD) and filters out out-of-domain leakage. *(Resolves FM 6.3)*
6. **[build_evidence](file:///C:/Users/C:/Users/stuti/Downloads/phd-shortlist%20(1)/phd-shortlist/shortlist/stages/finalize.py)**: Attaches verified papers and grants. Rejects personal fellowships (NIH F31/F32, MSCA) as PI grant evidence. *(Resolves FM 6.2)*
7. **[eligibility_ok](file:///C:/Users/C:/Users/stuti/Downloads/phd-shortlist%20(1)/phd-shortlist/shortlist/stages/finalize.py)**: Filters linked PhD positions by parsing unstructured vacancy text for citizenship, fee, or residency constraints (e.g., "UK only"). *(Resolves FM 6.4)*
8. **Ranking & Tiers**: Scores survivors based on topic relevance, seniority, and recency of publications, applying ranking priors from downstream feedback.
9. **Personalized `why_match`**: Generates a 2-3 sentence introductory hook citing specific PI works matched to the student's background.

---

## Data Sources & LLM Integration

* **OpenAlex Graph API**: Used as the primary academic data source. We query works, authors, and awards. No API key is required; the system integrates a sqlite-based local cache ([cache.py](file:///C:/Users/stuti/Downloads/phd-shortlist%20(1)/phd-shortlist/shortlist/sources/cache.py)) to ensure reproducibility and reduce network latency.
* **LLM Engine Wrapper**: Supports three plug-and-play LLM backends:
  * **Gemini** (default: `gemini-2.5-flash-lite` via `GEMINI_API_KEY`)
  * **Groq** (default: `llama-3.3-70b-versatile` via `GROQ_API_KEY`)
  * **Ollama** (offline: `llama3.1:8b` via `LLM_PROVIDER=ollama`)

---

## Quick Start & Installation

### 1. Setup Environment
```bash
# Clone the repository and install dependencies
pip install -r requirements.txt

# Create a .env file or export environment variables
export GEMINI_API_KEY="your-google-api-key"
export OPENALEX_EMAIL="your-email@domain.com" # Placed in OpenAlex polite pool
```

### 2. Run Pipeline
To run the end-to-end pipeline on a student profile and output a ranked shortlist:
```bash
python -m shortlist run --student sample_input/106419.json --out sample_output/106419.json
```

### 3. Run Feedback Loop (Bonus)
Ingest downstream outcomes (e.g., admitting, bounces, wrong person) to adjust future ranking priors:
```bash
python -m shortlist feedback --outcomes sample_input/outcomes.csv --out sample_output/priors.json
```

---

## Closing the Feedback Loop

Downstream outcomes (such as `ADMIT`, `REJECT`, `BOUNCE`, `WRONG_PERSON`) are processed by [feedback.py](file:///C:/Users/stuti/Downloads/phd-shortlist%20(1)/phd-shortlist/shortlist/feedback.py). 

We compute a multi-level Bayesian shrinkage score:
$$\text{Multiplier} = 1.0 + 0.4 \times \text{ShrunkReward}$$
This multiplier (bounded between `0.6` and `1.4`) is applied dynamically to candidate scores in subsequent pipeline runs:
* **Supervisor Level**: Corrects errors or validates individual matches.
* **Institution-Area Level**: Dampens whole university-topic subfields if wrong PIs are consistently surfaced.
* **Area Level**: Adjusts general expectations for specific research areas.
* **Bug Detection**: Severe failure modes (`BOUNCE` and `WRONG_PERSON`) are flagged for filter audits, indicating underlying disambiguation or contact extraction issues.

---

## Design Trade-offs & Limitations

* **Precision Over Recall**: The system prioritizes dropping borderline candidates (fail-closed) rather than maximizing coverage, aligning with the mentor evaluation metrics.
* **Last-Author Rule Limits**: Some disciplines (e.g., Mathematics, Computer Science, Economics) publish alphabetically rather than placing the PI in the last author slot.
* **Vacancy Ad Access**: The eligibility check requires vacancy ad text. Currently, the OpenAlex API lacks live job listings, so eligibility checks only run on entries that carry ad strings.

---

## Repository Structure

* [shortlist/pipeline.py](file:///C:/Users/stuti/Downloads/phd-shortlist%20(1)/phd-shortlist/shortlist/pipeline.py): Wires pipeline stages.
* [shortlist/schema.py](file:///C:/Users/stuti/Downloads/phd-shortlist%20(1)/phd-shortlist/shortlist/schema.py): Pydantic data schemas.
* [shortlist/stages/](file:///C:/Users/stuti/Downloads/phd-shortlist%20(1)/phd-shortlist/shortlist/stages/): Filter implementation stages.
* [shortlist/sources/](file:///C:/Users/stuti/Downloads/phd-shortlist%20(1)/phd-shortlist/shortlist/sources/): APIs, cache database, and LLM clients.
* [DECISIONS.md](file:///C:/Users/stuti/Downloads/phd-shortlist%20(1)/phd-shortlist/DECISIONS.md): Architectural decisions and data quality analysis.
* [schema.md](file:///C:/Users/stuti/Downloads/phd-shortlist%20(1)/phd-shortlist/schema.md): Output JSON structure documentation.
