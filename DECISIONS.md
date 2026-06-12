# DECISIONS.md

This document details the architectural decisions, design trade-offs, and strategies implemented to address the data quality challenges outlined in the PhD Shortlist Builder assignment. 

Guided by the primary grading rubric principle—**contamination is penalized heavier than coverage**—the system is designed as a strict, multi-stage "funnel of filters". Every gate defaults to **fail-closed**: when a candidate's identity, role, domain, or eligibility is ambiguous, they are dropped from the pipeline. 

All examples below refer to the pipeline output generated for student **106419** (Clinical Psychology; research interests: veteran/first-responder PTSD, disaster-survivor mental health, anthropology of Himalayan pilgrimage; target countries: US and Australia).

---

## 1. Core Data Quality Challenges Addressed

The system successfully resolves **7 distinct data quality challenges** across the pipeline, combining local heuristic filters with targeted LLM gating.

### Challenge 1: Same-Name-Different-Person Collisions (Section 6.1)
* **The Problem:** Common name strings (e.g., "Wei Wang", "Yu Meng", "Yang Shi", "Sharma") conflate unrelated researchers, resulting in mismatched profiles and embarrassing cold emails.
* **The Solution:** 
  1. **Decoupled Identity:** The pipeline never performs retrieval or filtering on raw name strings. Instead, it queries the **OpenAlex Author ID** (`Axxxxxxxxx`), which is already a disambiguated entity graph.
  2. **Topic Profile Similarity Check:** Before any LLM is called, the system performs a cheap local check (`disambiguation_ok` in `domain_gate.py`). We extract the top 10 topics associated with the author's OpenAlex profile, compute local sentence embeddings via `all-MiniLM-L6-v2`, and calculate the cosine similarity against the student's research interests. A threshold of `0.30` acts as a cheap, early-stage filter to drop authors whose general body of work (e.g., concrete materials science) deviates completely from the student's area.
* **Concrete Example:** For student `106419`, prominent PTSD researchers like **Kerry J. Ressler** (Harvard, ID `A5073581575`) and **Sarah R. Lowe** (Yale, ID `A5014541552`) are resolved as distinct IDs. Unrelated authors with overlapping surnames are filtered out at the embedding phase before incurring LLM API costs.

### Challenge 2: Career-Stage Errors: Graduate Students & Postdocs (Section 6.2)
* **The Problem:** Junior researchers (PhDs, postdocs) publish heavily as first authors but cannot supervise PhD students. Surfacing them leads to non-actionable matches.
* **The Solution:** We implement three combined structural heuristics in `resolve_pis.py`:
  1. **Last-Author Requirement:** The candidate must appear as the **last/corresponding author** on at least one paper within the retrieved search results for the student's area. In social and medical sciences (including clinical psychology), the last position is reserved for the PI/lab head, while trainees are first authors.
  2. **Career Span Constraints:** The researcher must have a publication history span of **$\ge 4$ years** (calculated from their active publication years in OpenAlex) and a cumulative **$\ge 8$ total works**.
* **Concrete Example:** This rule successfully eliminates 24-year-old grad students who only have first-author publications, ensuring the top of the shortlist contains established lab directors such as **Robert H. Pietrzak** (US VA, 170+ publications) and **Barbara O. Rothbaum** (Emory, 370+ publications).

### Challenge 3: Career-Stage Errors: Personal Fellowships (Section 6.2)
* **The Problem:** Personal awards (e.g., NIH F31/F32, UKRI studentships, MSCA postdoc grants) list the junior recipient as the lead investigator, mimicking PI status.
* **The Solution:** In `finalize.py`, the system implements a strict fellowship filter (`looks_like_fellowship`). When parsing grant evidence retrieved from OpenAlex, the funding title and description are searched for known junior award markers: `fellowship`, `studentship`, `f31`, `f32`, `msca`, `doctoral`. Any matching award is rejected as PI grant evidence.
* **Concrete Example:** If an author's only grant evidence consists of a personal fellowship (e.g., an NIH F31 doctoral fellowship), they fail to accumulate valid PI-level grant evidence and are down-ranked or dropped if they lack papers.

### Challenge 4: Wrong-Domain Leakage from Keyword Overlap (Section 6.3)
* **The Problem:** Literal keyword searches retrieve papers in unrelated disciplines (e.g., "trauma" in Roman literature vs. clinical PTSD; "DNA barcoding" in genomics vs. plant ecology; "biodegradable cartridges" in military munitions vs. biomaterials).
* **The Solution:** We implement a **Two-Stage Defense**:
  1. **Embedding Pre-filter (Local & Cheap):** Fast local vector comparison of paper topics against the target area using `all-MiniLM-L6-v2`.
  2. **Structured LLM Domain Gate (Global & Smart):** Surviving candidates are batched (25 at a time) and audited by a structured LLM prompt (`_GATE_SYS` in `domain_gate.py`). The prompt is primed with the exact trap categories from the assignment instructions. The LLM must classify the PI's discipline (e.g., humanities vs. STEM vs. clinical) and output a boolean verdict (`matches`) along with a structured `reason`.
* **Concrete Example:** In the sample run, the keyword "PTSD veterans" matched OpenAlex topics under "Maternal and Perinatal Health". The LLM domain gate identified the discipline mismatch and set `matches=false`, removing the candidate. In the pilgrimage area, this gate dropped economics-of-tourism researchers who merely used the word "pilgrim" as a tourist demographic, preserving the anthropological focus.

### Challenge 5: Eligibility Filters in Free-Text Ads (Section 6.4)
* **The Problem:** PhD advertisements often contain citizenship restrictions ("UK only", "EU residents", "home fees only") buried in the text. Surfacing these to ineligible international students wastes critical application attempts.
* **The Solution:** The pipeline includes an LLM extraction gate (`eligibility_ok` in `finalize.py`). It processes free-text vacancy descriptions and returns a structured JSON: `{"international_eligible": bool, "note": str}`. If phrases indicating domestic limits are detected, the position is flagged as ineligible and filtered out.
* **Concrete Example:** A vacancy listing specifying "funding only covers UK/home fees" is parsed by the model, setting `international_eligible=false`. The student (e.g., an Indian national) is shielded from applying to a position they cannot hold.

### Challenge 6: Evidence Integrity & No Guessed Contacts (Sections 4 & 5)
* **The Problem:** Recommending a supervisor without contact details or concrete academic evidence erodes the trust of domain mentors. Guessing email patterns leads to high bounce rates.
* **The Solution:** 
  1. **Strict Evidence Check:** Every supervisor on the shortlist must have at least one verifiable paper or grant. PIs with zero valid evidence are dropped.
  2. **Resolvable Links:** Every piece of evidence carries a verified URL (DOIs preferred for papers, funding search links for grants).
  3. **Null Contacts over Guessed Contacts:** If a contact email cannot be verified from OpenAlex or official university graphs, it is set to `null` instead of being guessed.
* **Concrete Example:** 100% of the entries in `sample_output/106419.json` carry valid paper and/or grant details with resolvable links (e.g., DOIs linking to Nature/JAMA publications).

### Challenge 7: Closing the Feedback Loop (Section 10 - Bonus)
* **The Problem:** The pipeline must learn from downstream outcomes (e.g., email bounces, wrong person, positive reply) to automatically improve future runs.
* **The Solution:** We built a feedback ingestion engine (`feedback.py`) that calculates ranking priors:
  1. **Outcome Reward Mapping:** Outcomes are mapped to a numerical scale: `ADMIT` (+1.0), `INTERVIEW` (+0.8), `WRONG_PERSON` (-1.0), and `BOUNCE` (-0.5).
  2. **Multi-Level Shrinkage:** Priors are computed and smoothed using Bayesian shrinkage toward the global mean across three levels: supervisor ID, institution-area combination, and general research area.
  3. **Score Multipliers:** These priors are saved to `priors.json` and loaded during subsequent runs to apply a multiplier (`[0.6, 1.4]`) to candidate scores.
* **Concrete Example:** If an institution-area (e.g., `University of Melbourne::Pilgrim`) yields multiple `WRONG_PERSON` reports, its prior drops, lowering the score of future candidates from that institution in that area. If a supervisor ID (e.g., `A5012340006`) returns a `BOUNCE` (email invalid), it is flagged for review, and its prior is severely penalized.

---

## 2. Technical and Design Trade-offs

| Design Choice | Rationale | Trade-off / Risk | Mitigation |
|---|---|---|---|
| **Last-Author Heuristic for PIs** | Simple, reliable, and highly accurate for biomedical, psychological, and STEM fields. | Inaccurate for fields with alphabetical author conventions (e.g., Economics, Mathematics, CS). | In a multi-disciplinary setup, we would make this heuristic discipline-aware using OpenAlex's sub-field classification. |
| **Local Embeddings before LLM Gating** | Dramatically reduces API costs and runtime latency by dropping obvious mismatches early. | Might filter out a multidisciplinary researcher whose main topics are slightly outside the cosine threshold. | We set the similarity threshold to a loose `0.30` to avoid false negatives at the early stage. |
| **Strict Evidence Constraint** | Protects mentor trust; ensures every recommendation is backed by verifiable research. | Drops newly appointed PIs who have active labs but haven't updated their OpenAlex publication graph. | Mitigated by checking both papers (past 6 years) and active grants. |
| **Decoupled CLI & Priors** | Separation of concerns: training priors (`feedback`) is isolated from scoring (`run`). | Command line users must run feedback generation as a separate step before executing a shortlist. | Added clear instructions in the README and CLI parser arguments. |

---

## 3. Stated Areas Coverage and Imbalance

An honest audit of `sample_output/106419.json` reveals a significant distribution imbalance:
* **PTSD and Trauma:** ~90 recommendations.
* **Disaster Mental Health:** ~76 recommendations.
* **Anthropology of Himalayan Pilgrimage:** Only 3 recommendations.

### Why this is the correct behavior:
We deliberately rejected enforcing artificial per-area quotas (e.g., forcing at least 15 pilgrimage matches). Enforcing a minimum count for a niche topic in a constrained geography (Australia and US) would require lowering the LLM domain gate threshold. This would lead to wrong-domain leakage (e.g., admitting tourism economists or general South Asian historians), violating the core requirement: **contamination is penalized heavier than coverage**. We choose to surface only the genuine, highly relevant anthropologists (e.g., Craig Jeffrey) and leave the niche area thin.

---

## 4. Next Steps for Production Maturity

If given more than 72 hours, we would prioritize the following:
1. **Live Position Feeds:** Integrate RSS/API feeds from FindAPhD and university portal crawlers to populate the `linked_programs` field with active vacancies.
2. **ORCID Cross-Referencing:** Harden name disambiguation and recover verified contact emails by linking OpenAlex profiles directly with ORCID registries.
3. **Discipline-Specific PI Rules:** Adjust the author position checks dynamically based on the target area's publishing standards (last-author for STEM/Psychology, alphabetical/first-author for Economics/Math).
