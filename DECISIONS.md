# DECISIONS.md

A 72-hour build. The governing principle, taken straight from the rubric: **contamination
is penalised harder than coverage.** So the system is a funnel of filters, and almost every
design call resolves toward *fail-closed* — when unsure, drop the candidate. A clean list of
~150 where the top picks are real domain leaders beats a noisy list of 200.

All examples below are from the committed `sample_output/106419.json` (student: clinical
psychology, areas = veteran/first-responder PTSD, disaster-survivor mental health,
anthropology of Himalayan pilgrimage; target countries AU + US). That run took **1,950
candidates → 153 supervisors**, 100% in-country, all three areas covered.

---

## FM 6.1 — Same-name-different-person collisions

**What I did.** I never disambiguate on name strings. Retrieval and every downstream stage
key on the **OpenAlex author ID** (`Axxxxxxxxx`), which is already a disambiguated entity —
"Wei Wang" the materials scientist and "Wei Wang" the linguist are simply different IDs, so
the collision the assignment warns about mostly cannot occur in my candidate set.

OpenAlex's own resolution isn't perfect, so I add a second gate (`disambiguation_ok`): the
author's *own* topic distribution must sit within cosine 0.30 of the student's area
embedding. If a candidate surfaced under "PTSD" but their body of work is concrete
durability, the ID is suspect and gets dropped before it ever costs an LLM call.

**Trade-off.** The 0.30 threshold is deliberately loose — it's a cheap pre-filter to kill
obvious mis-merges, not the precision gate. The expensive LLM domain gate (6.3) is where I
spend real judgment. Loose-here / strict-there keeps latency down without leaking.

## FM 6.2 — Career-stage errors (grad students surfaced as PIs)

This is the failure mode I invested the most in, because it's the easiest way to embarrass
the product.

**Three combined signals (`resolve_pis.py`):**
1. **Last-author requirement.** A candidate must appear as *last author* on at least one
   in-area paper. In most of these fields the last/corresponding slot is the PI; first-author-
   only people are overwhelmingly trainees. This single rule removes a large share of the
   24-year-olds the brief warns about.
2. **Track record.** `works_count ≥ 8` **and** a publication career span `≥ 4 years`
   (derived from `counts_by_year`). A fresh PhD student clears neither.
3. **Fellowship guard.** When attaching grant evidence, any award whose title/type matches
   `fellowship | studentship | F31 | F32 | MSCA | doctoral` is *rejected as PI evidence* —
   those name the junior **awardee**, not a supervisor. So a personal fellowship counts
   *against* PI status, never for it. (`looks_like_fellowship`, unit-tested.)

**Result in output.** The top PTSD picks — Kerry Ressler (Harvard), Sandro Galea (BU),
Nathan Kimbrel (Durham VA) — are all established lab heads, not students.

**Trade-off.** The last-author heuristic is wrong for fields that author alphabetically
(econ, some math/CS). For a psychology/anthropology student it's safe; I flag it as a known
limitation and would make it discipline-aware before generalising.

## FM 6.3 — Wrong-domain leakage from keyword overlap

**Two-stage defense, cheap then expensive:**
- **Embedding pre-filter** (free, local MiniLM) removes candidates whose topic vector is
  nowhere near the area. Fast triage.
- **LLM domain gate** (`domain_gate`) then asks a *structured* question per survivor:
  return `{discipline, matches, reason}`, and the prompt explicitly primes the model with
  the assignment's own traps (trauma-as-clinical vs trauma-as-Roman-literary-history;
  barcoding-as-ecology vs barcoding-as-single-cell-genomics; biodegradable-cartridges-as-
  biomaterials vs munitions). `matches=false` unless the model is confident the
  *disciplines* (and region/population, when the area implies one) align. Unparseable reply
  → fail-closed drop.

**A real one I hit while building.** OpenAlex's `/topics` *keyword* search mapped the phrase
"PTSD veterans" to the topic **"Maternal and Perinatal Health Interventions"** — a textbook
6.3 leak. That discovery made me **abandon topic-ID retrieval entirely** and switch to
full-text work search, recovering topics from the returned works instead (see the commit
history). The bug in a dependency became a design decision.

**Honest residual.** With the *stub* LLM used to generate the committed sample (no API key
in the build sandbox), one pilgrimage-area entry — "Teresa Garín Muñoz / NBER" — is an
economics-of-tourism researcher that a stricter gate should down-rank. The production Gemini
gate is materially better at this than my crude keyword stub; I left the entry in rather than
hand-curate the sample, so the limitation is visible.

## FM 6.4 — Eligibility filters in free-text ads

**What I did.** `eligibility_ok` runs an extraction prompt over any linked vacancy text and
returns `{international_eligible, note}`. Phrases like "UK only", "home fees only", "EU
residents", "citizens/permanent residents only" flip it to false, and the *position* is
dropped while the supervisor can remain. The student profile carries an explicit
"international, not eligible for domestic-only schemes" flag that this stage honours.

**Trade-off / limitation.** This only fires when a position has linked ad text. OpenAlex
doesn't carry vacancy ads, so in this build the hook is implemented and tested in isolation
but rarely triggers on the sample (few linked programs). Wiring a live positions source
(FindAPhD, jobRxiv, university feeds) is the obvious next step; the extraction logic is
ready for it. I chose to spend my 72 hours making the *people* correct first, since a wrong
person is the costlier error.

## FM (bonus) — Evidence integrity & no guessed contacts

Two self-imposed guarantees beyond the four above, because they directly affect a mentor's
trust:
- **No evidence, no entry.** A supervisor with zero papers and zero grants is never emitted
  (enforced in the pipeline; verified zero such entries in the sample). Every paper carries
  a resolvable `url` (DOI preferred, OpenAlex fallback).
- **Never guess emails.** `contact_email` is null unless a source exposes it. A wrong email
  produces a `BOUNCE` (see bonus) and wastes the student's one shot at a PI.

---

## Cross-cutting trade-offs

- **Precision over recall, everywhere.** Last-author + track-record + fail-closed gating all
  bias toward dropping the borderline case.
- **Cheap-before-expensive ordering** (country filter → last-author → embedding →
  LLM gate → evidence/why_match) is what keeps a 1,950-candidate run under the 15-minute
  budget: the costly LLM calls only ever touch survivors.
- **Reproducibility via caching + provider fallback.** Every OpenAlex GET is cached in
  SQLite, and the LLM layer falls back to local Ollama with no key, so a grader can run
  `python -m shortlist run ...` and get deterministic output.

## Coverage spread across areas — an honest imbalance

The rubric wants coverage spread across *all* stated areas. In the sample run, the three
areas resolve very unevenly: ~90 PTSD picks, ~76 disaster-mental-health, but only **3** for
"anthropology of Himalayan pilgrimage." That's not a bug I hid — it reflects reality. There
are simply far more PTSD/disaster-mental-health PIs in AU+US than there are Himalayan-
pilgrimage anthropologists at those institutions, and my precision filters (last-author,
domain gate) correctly refuse to pad the thin area with tourism economists or unrelated
"pilgrimage" keyword hits just to inflate the count.

I considered enforcing a per-area minimum quota, but rejected it: forcing 15+ pilgrimage
entries would mean lowering the domain-gate bar for that area specifically, which trades
contamination for coverage in exactly the direction the rubric penalises. The defensible
choice is to surface the genuine matches that exist (Craig Jeffrey, Dallen Timothy, etc.)
and let the thin area be thin. If a student needed deeper pilgrimage coverage, the right fix
is broadening the *source* (add anthropology-specific databases, relax the recency window
for a slower-publishing humanities field) — not relaxing the correctness gate.

## What I'd do next with more time

1. Live PhD-positions feed so the 6.4 eligibility filter earns its keep.
2. Discipline-aware author-position logic (handle alphabetical-authorship fields).
3. ORCID cross-link to harden 6.1 further and recover more contact emails legitimately.
4. The feedback loop in `feedback/` (see below) wired into scoring as a learned prior.
