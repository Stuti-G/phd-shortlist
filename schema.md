# Output Schema

The shortlist is a single JSON object validated against `shortlist/schema.py`
(pydantic). Top level:

```jsonc
{
  "meta":  { ...ShortlistMeta },
  "supervisors": [ { ...Supervisor }, ... ]   // ranked best-first, 50–200 entries
}
```

## `meta`

| field | type | notes |
|---|---|---|
| `student_id` | string | from input profile |
| `generated_at` | string (ISO-8601) | run timestamp |
| `target_countries` | string[] | hard constraint applied during retrieval |
| `stated_areas` | string[] | the 3–5 research areas we matched against |
| `total_candidates_retrieved` | int | candidates before filtering |
| `total_after_filters` | int | survivors → drives the contamination/coverage trade-off |
| `llm_provider` | string | `gemini` / `ollama` — for reproducibility |
| `pipeline_version` | string | semver |

## `supervisors[]`

| field | type | notes |
|---|---|---|
| `supervisor_id` | string | **OpenAlex author ID** (already disambiguated), e.g. `A5031856973` |
| `name` | string | |
| `institution` | string | |
| `country` | string | **guaranteed within `target_countries`** (req #2) |
| `contact_email` | string \| null | only when obtainable; never guessed |
| `research_focus` | string | the PI's actual focus, summarised |
| `matched_area` | string | which stated area this PI maps onto |
| `tier` | enum \| null | `reach` / `target` / `safety` |
| `score` | float | 0–1, ranking transparency |
| `papers[]` | PaperEvidence | see below; every entry has a resolvable `url` |
| `grants[]` | GrantEvidence | lead-investigator grants only |
| `linked_programs[]` | LinkedProgram | open positions with eligibility note |
| `why_match` | string | cites **specific** PI work vs the student (req #4) |

### `PaperEvidence`
`title`, `year`, `doi`, `openalex_id`, `url`, `is_last_author` (bool — our core PI signal).

### `GrantEvidence`
`title`, `funder`, `funder_country` (region sanity-check), `award_id`,
`funding_type` (fellowships filtered upstream), `url`.

### `LinkedProgram`
`title`, `url`, `eligibility_note` (what the eligibility filter concluded).

## Guarantees

- **Country adherence:** every `country` ∈ `target_countries`. Enforced at retrieval and
  re-checked before write. A breach is a hard validation failure.
- **Evidence-backed:** a supervisor with zero papers *and* zero grants is never emitted.
- **No guessed contacts:** `contact_email` is null unless found in a source.
