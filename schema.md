# Output Schema

This document defines the schema of the JSON shortlist emitted by the PhD Shortlist Builder. The output is structured to ensure machine readability and validation against Pydantic models defined in [shortlist/schema.py](file:///C:/Users/stuti/Downloads/phd-shortlist%20(1)/phd-shortlist/shortlist/schema.py).

---

## 1. Top-Level Structure

The top-level JSON object consists of metadata about the query execution and a list of ranked supervisor recommendation objects.

```jsonc
{
  "meta": {
    // ... ShortlistMeta Object
  },
  "supervisors": [
    // ... List of Supervisor Objects (ranked best-first, 50-200 entries)
  ]
}
```

---

## 2. Object Definitions

### `meta` (ShortlistMeta)
Metadata concerning the pipeline execution run, used to ensure reproducibility and audit capabilities.

| Field | Type | Description |
| :--- | :--- | :--- |
| `student_id` | `string` | Unique identifier for the student, matching the input profile. |
| `generated_at` | `string` | ISO-8601 UTC timestamp of the pipeline run completion. |
| `target_countries` | `array of strings` | List of target ISO country codes used as a hard filter (e.g., `["AU", "US"]`). |
| `stated_areas` | `array of strings` | The student's stated research areas matched in this run. |
| `total_candidates_retrieved` | `integer` | Count of candidates retrieved from OpenAlex before filtering. |
| `total_after_filters` | `integer` | Count of candidates surviving all filters and written to the shortlist. |
| `llm_provider` | `string` | The LLM backend used (`gemini`, `groq`, `ollama`, or `stub`). |
| `pipeline_version` | `string` | Semantic version of the builder pipeline. |

---

### `supervisors[]` (Supervisor)
A ranked recommendation representing a verified PI.

| Field | Type | Description |
| :--- | :--- | :--- |
| `supervisor_id` | `string` | Unique disambiguated **OpenAlex Author ID** (e.g., `A5073581575`). |
| `name` | `string` | Full display name of the researcher. |
| `institution` | `string` | Verified primary institutional affiliation. |
| `country` | `string` | ISO country code of the institution (guaranteed to match `target_countries`). |
| `contact_email` | `string \| null` | Verified institutional contact email. Null if unavailable; **never guessed**. |
| `research_focus` | `string` | Comma-separated list of the researcher's top active topics. |
| `matched_area` | `string` | Stated student research interest this candidate was matched against. |
| `tier` | `string \| null` | Recommendation tier based on score: `"reach"`, `"target"`, or `"safety"`. |
| `score` | `float` | Quality score ($0.0 - 1.0$) used for ranking, computed via seniority, recency, and evidence. |
| `papers` | `array of PaperEvidence` | Verified recent publications by the candidate matching the research area. |
| `grants` | `array of GrantEvidence` | Active funding grants where the candidate is the Principal Investigator. |
| `linked_programs` | `array of LinkedProgram` | Open PhD vacancy listings with eligibility checks. |
| `why_match` | `string` | A 2-3 sentence personalized outreach blurb citing specific PI papers. |

---

### `PaperEvidence`
Verifiable academic paper backing the supervisor's active engagement in the matched area.

| Field | Type | Description |
| :--- | :--- | :--- |
| `title` | `string` | Title of the publication. |
| `year` | `integer \| null` | Year of publication. |
| `doi` | `string \| null` | Resolvable DOI URL. |
| `openalex_id` | `string` | Resolvable OpenAlex Work URL. |
| `url` | `string` | Direct web link to the work (prefers DOI, falls back to OpenAlex ID). |
| `is_last_author` | `boolean` | `true` if the PI is in the last/corresponding author slot (our core PI heuristic). |

---

### `GrantEvidence`
Active funding or research grants where the supervisor is verified as the Principal Investigator (junior personal fellowships are excluded).

| Field | Type | Description |
| :--- | :--- | :--- |
| `title` | `string` | Title of the funded project. |
| `funder` | `string \| null` | Name of the funding body (e.g., National Science Foundation). |
| `funder_country` | `string \| null` | ISO country code of the funder, used as a region sanity check. |
| `award_id` | `string \| null` | Official award or grant reference ID. |
| `funding_type` | `string \| null` | Funding category designation (e.g., `"grant"`, `"research"`). |
| `url` | `string \| null` | Direct link to the public award record. |

---

### `LinkedProgram`
Open PhD positions or projects affiliated with the supervisor.

| Field | Type | Description |
| :--- | :--- | :--- |
| `title` | `string` | Title of the position or open research program. |
| `url` | `string \| null` | Link to the vacancy advertisement. |
| `eligibility_note` | `string \| null` | Explanation of parsed citizenship, visa, or fee restrictions. |

---

## 3. Structural Guarantees

* **Country Adherence**: The `country` field of every supervisor is guaranteed to reside within the student's `target_countries`. Any breach throws a validation exception.
* **Evidence Integrity**: A supervisor is only emitted if they possess **at least one** verified paper or grant. PIs lacking both papers and grants are discarded to maintain list quality.
* **No Email Guessing**: The system never guesses email patterns. If a contact email is not explicitly returned by academic registries or landing scraping, it is written as `null` to avoid email bounces.

---

## 4. Concrete Schema Example

The following is a verified, valid JSON output fragment:

```json
{
  "meta": {
    "student_id": "106419",
    "generated_at": "2026-06-10T13:50:41.949681+00:00",
    "target_countries": [
      "AU",
      "US"
    ],
    "stated_areas": [
      "PTSD and trauma in veterans and first responders",
      "Mental health interventions for disaster survivors",
      "Anthropology of Himalayan pilgrimage and wellbeing"
    ],
    "total_candidates_retrieved": 1950,
    "total_after_filters": 169,
    "llm_provider": "gemini",
    "pipeline_version": "0.1.0"
  },
  "supervisors": [
    {
      "supervisor_id": "A5073581575",
      "name": "Kerry J. Ressler",
      "institution": "Harvard University",
      "country": "US",
      "contact_email": null,
      "research_focus": "Stress Responses and Cortisol, Posttraumatic Stress Disorder Research, Memory and Neural Mechanisms, Traumatic Brain Injury Research, Behavior",
      "matched_area": "PTSD and trauma in veterans and first responders",
      "tier": "target",
      "score": 0.925,
      "papers": [
        {
          "title": "Transcriptome-wide association study of post-trauma symptom trajectories identified GRIN3B as a potential biomarker for PTSD development",
          "year": 2021,
          "doi": "https://doi.org/10.1038/s41386-021-01073-8",
          "openalex_id": "https://openalex.org/W3174681005",
          "url": "https://doi.org/10.1038/s41386-021-01073-8",
          "is_last_author": true
        }
      ],
      "grants": [
        {
          "title": "STTR Phase I: Feasibility and proof of concept of a non-invasive treatment for PTSD",
          "funder": "National Science Foundation",
          "funder_country": "US",
          "award_id": "1521347",
          "funding_type": "grant",
          "url": "https://www.nsf.gov/awardsearch/showAward?AWD_ID=1521347"
        }
      ],
      "linked_programs": [
        {
          "title": "Postdoctoral research fellowship in translational neurobiology of PTSD",
          "url": "https://harvard.edu/postdoc-vacancy-ptsd",
          "eligibility_note": "Open to international candidates with a molecular psychology background"
        }
      ],
      "why_match": "Kerry J. Ressler works directly on your stated area; their paper \"Transcriptome-wide association study of post-trauma symptom trajectories...\" overlaps your PTSD and disaster-survivor fieldwork, offering a strong hook for your email."
    }
  ]
}
```
