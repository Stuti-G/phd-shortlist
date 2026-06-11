"""Stages 4 & 5 — disambiguation (FM 6.1) and the domain gate (FM 6.3).

FM 6.1 (same-name-different-person): OpenAlex already resolves authors into stable IDs, so
"Wei Wang" the materials scientist and "Wei Wang" the linguist are different IDs. That does
most of the work for free. But ID resolution can still mis-merge, so I add a topic-overlap
check: the author's OWN topic distribution must actually contain the student's area. If a
"PTSD" candidate's body of work is 90% concrete durability, the ID is suspect — drop it.

FM 6.3 (wrong-domain leakage): keyword overlap is a liar. "biodegradable plastic cartridges"
is military ammo; a "trauma-informed" grant can be Roman literary history. So after the
cheap embedding prefilter, I spend one LLM call per surviving PI asking a structured
discipline + region question: does this researcher's ACTUAL work map onto the student's
area? The model must answer with a discipline label and a yes/no, and justify against the
PI's real focus — not the matching keyword.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..sources.llm import LLM
from .resolve_pis import ResolvedPI

# Lazy global so we load the embedding model once, not per call.
_EMBEDDER = None


def _embedder():
    global _EMBEDDER
    if _EMBEDDER is None:
        from sentence_transformers import SentenceTransformer
        _EMBEDDER = SentenceTransformer("all-MiniLM-L6-v2")
    return _EMBEDDER


def _cos(a, b) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))


# ----- Stage 4: topic-overlap disambiguation -----------------------------------

def author_topic_names(rec: dict) -> list[str]:
    return [t.get("display_name", "") for t in rec.get("topics", [])[:10]]


def disambiguation_ok(pi: ResolvedPI, area_embedding) -> bool:
    """The PI's own topic distribution must be semantically near the student's area.
    Cheap embedding check; catches mis-merged IDs and obvious off-topic surfacing."""
    topics = author_topic_names(pi.author_record)
    if not topics:
        return False
    emb = _embedder().encode(topics)
    best = max(_cos(area_embedding, t) for t in emb)
    return best >= 0.30   # tuned loose; the LLM gate below is the strict one


# ----- Stage 5: LLM domain gate -------------------------------------------------

_GATE_SYS = (
    "You are a strict academic matching auditor. You receive a student's research area and "
    "a NUMBERED LIST of researchers (each with their actual topics + a sample paper title). "
    "For EACH researcher, decide if they genuinely work in the student's DISCIPLINE and "
    "(if the area implies one) REGION/POPULATION. "
    "Beware keyword overlap across disciplines: e.g. 'trauma' in clinical psychology vs "
    "Roman literary history; 'barcoding' in plant ecology vs single-cell genomics; "
    "'biodegradable cartridges' in biomaterials vs military munitions. "
    "Return JSON: {\"verdicts\": [{\"i\": int, \"discipline\": str, \"matches\": bool, "
    "\"reason\": str}, ...]} with one entry per researcher index. "
    "Set matches=false unless you are confident the disciplines align."
)

# Default PIs-per-call. Gemini's 1M TPM swallows big batches; Groq's free 6K TPM does not,
# so we shrink per provider via llm.batch_size(). Override with GATE_BATCH_SIZE env var.
GATE_BATCH_SIZE = 25


def _pi_line(idx: int, pi: ResolvedPI) -> str:
    sample_title = pi.in_area_works[0].get("title", "") if pi.in_area_works else ""
    topics = ", ".join(author_topic_names(pi.author_record)) or "(none)"
    return f"[{idx}] topics: {topics} | sample paper: {sample_title}"


def domain_gate_batch(pis: list[ResolvedPI], llm: LLM) -> list[tuple[ResolvedPI, str]]:
    """Judge PIs in batches grouped by student area (so the question is coherent within a
    call). Returns the survivors with their reason. Fail-closed: any PI the model doesn't
    return a clear matches=true for is dropped."""
    survivors: list[tuple[ResolvedPI, str]] = []
    batch_size = llm.batch_size(GATE_BATCH_SIZE)  # provider-aware: small for Groq

    # Group by area first — a batch should ask one area-question, not mix areas.
    by_area: dict[str, list[ResolvedPI]] = {}
    for p in pis:
        by_area.setdefault(p.area, []).append(p)

    for area, group in by_area.items():
        for start in range(0, len(group), batch_size):
            chunk = group[start:start + batch_size]
            listing = "\n".join(_pi_line(i, p) for i, p in enumerate(chunk))
            user = f"Student area: {area}\nResearchers:\n{listing}"
            resp = llm.complete_json(_GATE_SYS, user)

            verdicts = {}
            if isinstance(resp, dict) and isinstance(resp.get("verdicts"), list):
                for v in resp["verdicts"]:
                    if isinstance(v, dict) and "i" in v:
                        verdicts[v["i"]] = v

            for i, p in enumerate(chunk):
                v = verdicts.get(i)
                # fail-closed: missing or non-matching verdict -> dropped
                if v and bool(v.get("matches")):
                    survivors.append((p, str(v.get("reason", ""))))
    return survivors


def domain_gate(pi: ResolvedPI, llm: LLM) -> tuple[bool, str]:
    """Single-PI gate, kept for tests and one-off use. The pipeline uses the batch path."""
    sample_title = pi.in_area_works[0].get("title", "") if pi.in_area_works else ""
    topics = ", ".join(author_topic_names(pi.author_record)) or "(none)"
    user = (
        f"Student area: {pi.area}\nResearchers:\n"
        f"[0] topics: {topics} | sample paper: {sample_title}"
    )
    resp = llm.complete_json(_GATE_SYS, user)
    if isinstance(resp, dict) and isinstance(resp.get("verdicts"), list):
        for v in resp["verdicts"]:
            if isinstance(v, dict) and v.get("i") == 0:
                return bool(v.get("matches")), str(v.get("reason", ""))
    return False, "gate-unparseable -> dropped (fail-closed)"


@dataclass
class GatedPI:
    pi: ResolvedPI
    domain_reason: str
