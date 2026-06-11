# PhD Shortlist Builder

Ingests a student profile and produces a ranked JSON shortlist of PhD **supervisors**
(verified PIs, not grad students) + linked programs, each carrying real paper/grant
evidence and a personalised `why_match`.

The design philosophy is taken straight from the grading rubric: **contamination is
weighted heavier than coverage.** So the pipeline is built as a *funnel of filters* —
every stage removes bad candidates rather than chasing volume. A clean list of 60 beats
a noisy list of 150.

## How it works

```
student.json
   |
   v
[1] parse_profile     free-text interests -> normalised OpenAlex Topic IDs
[2] retrieve          OpenAlex /works, filtered by country (HARD) + topic + recency
[3] resolve_pis       drop non-PIs: last-author check, career span, fellowship filter   (FM 6.2)
[4] disambiguate      OpenAlex author IDs + verify topic distribution matches student    (FM 6.1)
[5] domain_gate       LLM discipline/region check: does the PI's real work map?          (FM 6.3)
[6] evidence          attach verifiable papers + grants with links
[7] eligibility       LLM extracts citizenship limits from vacancy text, drops ineligible (FM 6.4)
[8] rank_tier         score by topic match x seniority x recency -> reach/target/safety
[9] why_match         LLM cites SPECIFIC PI papers against the student profile
   |
   v
shortlist.json  (validated against schema.md)
```

Each stage maps to a named failure mode in the assignment (FM = Section 6). See
`DECISIONS.md` for the trade-offs.

## Data sources

- **OpenAlex** (https://openalex.org) — primary academic graph. Authors are already
  disambiguated into stable IDs (`Axxxx`), works carry topics + country-coded
  affiliations, and awards now expose `lead_investigator` / `funding_type`, which we
  exploit for PI resolution. Free, no key; we use the polite pool (set `OPENALEX_EMAIL`).
- **LLM** — provider-agnostic wrapper, chosen via `LLM_PROVIDER` (or auto-detected from
  whichever key is set). Three backends:
  - **Gemini** free tier (`GEMINI_API_KEY`) — default; 1M tokens/min suits big batches.
  - **Groq** free tier (`GROQ_API_KEY`) — Llama 3.3 70B, very fast, separate daily quota;
    a good fallback when Gemini's daily limit is exhausted.
  - **Ollama** (local, no key) — fully offline so the repo runs end-to-end with zero paid
    dependencies.
  All three are batched (one call per ~25 PIs at the domain gate) and retry on 429.

## Quick start

```bash
pip install -r requirements.txt

# Option A (recommended): free Gemini key from https://aistudio.google.com
export GEMINI_API_KEY=...        # provider auto-detected
export OPENALEX_EMAIL=you@example.com   # polite pool, faster + nicer

# Option B: free Groq key from https://console.groq.com (fast, separate quota)
export GROQ_API_KEY=...
export LLM_PROVIDER=groq

# Option C: fully offline, no account
#   install ollama, then: ollama pull llama3.1:8b
export LLM_PROVIDER=ollama

# one command, end to end:
python -m shortlist run --student sample_input/106419.json --out sample_output/106419.json
```

## Bonus — closing the feedback loop

After shortlists are used, an outcomes CSV comes back (`ADMIT`, `REJECT`, `WRONG_PERSON`,
`BOUNCE`, ...). `shortlist/feedback.py` ingests it and produces interpretable ranking priors:

```bash
python -m shortlist feedback --outcomes sample_input/outcomes.csv --out sample_output/priors.json
```

Design in brief (full reasoning in DECISIONS.md):

- Each outcome maps to a reward in `[-1, 1]`, ordered so **contamination hurts most**
  (`WRONG_PERSON` = -1.0, `BOUNCE` = -0.5, `ADMIT` = +1.0).
- Priors are computed at three granularities — supervisor, institution×area, area — with
  shrinkage toward the global mean, so a single noisy outcome can't swing a key. The blended
  prior becomes a bounded score multiplier (`[0.6, 1.4]`) applied in stage 8.
- `WRONG_PERSON` and `BOUNCE` are treated as **bugs in our own output**, not just unlucky
  matches: they're flagged for filter review, closing the loop back onto FM 6.1 / 6.3 and
  the email-finding logic.

Pass the priors into a later run to apply them:

```python
from shortlist.feedback import build_priors
priors = build_priors("outcomes.csv")
run_pipeline(profile, priors=priors)   # scores are nudged by past outcomes
```

## Trade-offs (summary; full version in DECISIONS.md)

- **Precision over recall.** Several stages are deliberately aggressive filters. We would
  rather drop a borderline-correct PI than admit a wrong-person.
- **Author-ID-first disambiguation.** We lean on OpenAlex's existing author resolution
  instead of rolling our own, then add a topic-overlap check on top. Cheap and robust.
- **Cheap-then-expensive gating.** An embedding prefilter removes obvious domain
  mismatches before we spend an LLM call on the subtle ones — keeps us under the 15-min
  latency budget.
- **Caching.** All OpenAlex responses are cached in SQLite so reruns are fast and
  reproducible.

## Known limitations

- Contact emails are only surfaced when OpenAlex/landing pages expose them; we never guess.
- Grant region inference relies on funder country, which is occasionally missing.
- Vacancy/eligibility text is only as good as the linked ad; unlinked positions are skipped.

## Repo layout

```
shortlist/
  sources/      OpenAlex client, LLM wrapper, cache
  stages/       one module per pipeline stage above
  pipeline.py   wires the stages together
  schema.py     pydantic models (source of truth for schema.md)
  cli.py        `python -m shortlist run ...`
sample_input/   example student profile
sample_output/  example shortlist JSON
tests/
```
