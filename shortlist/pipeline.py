from __future__ import annotations

import sys
from datetime import datetime, timezone

from .schema import Shortlist, ShortlistMeta
from .sources.llm import LLM
from .sources.openalex import OpenAlex
from .stages.domain_gate import (GatedPI, disambiguation_ok, domain_gate_batch, _embedder)
from .stages.finalize import (assign_tier, build_evidence, score_pi, to_supervisor,
                              write_why_match_batch, _why_fallback)
from .stages.parse_profile import parse_profile
from .stages.resolve_pis import resolve_pis
from .stages.retrieve import retrieve


def run_pipeline(profile: dict, oa: OpenAlex | None = None, llm: LLM | None = None,
                 priors=None) -> Shortlist:
    oa = oa or OpenAlex()
    llm = llm or LLM()

    target_countries = profile["target_countries"]
    student_summary = _student_summary(profile)

    def log(msg: str) -> None:
        print(f"  [pipeline] {msg}", file=sys.stderr, flush=True)

    log(f"provider={llm.provider} model={llm.model}")

    log("parsing profile into search queries...")
    area_queries = parse_profile(profile, oa, llm)

    log("retrieving candidates from OpenAlex...")
    candidates = retrieve(area_queries, target_countries, oa)
    n_retrieved = len({c.author_id for c in candidates})
    log(f"retrieved {n_retrieved} unique authors")

    log("resolving PIs (seniority / career-stage filter)...")
    pis = resolve_pis(candidates, oa)
    log(f"{len(pis)} candidates passed PI resolution")

    area_emb = {aq.area: _embedder().encode(aq.area) for aq in area_queries}
    pis = [p for p in pis if disambiguation_ok(p, area_emb.get(p.area, _embedder().encode(p.area)))]
    log(f"{len(pis)} passed disambiguation; running domain gate...")

    gated: list[GatedPI] = [
        GatedPI(pi=p, domain_reason=reason)
        for p, reason in domain_gate_batch(pis, llm)
    ]
    log(f"{len(gated)} passed domain gate; building evidence + why_match...")
    staged = []  
    for gp in gated:
        papers, grants = build_evidence(gp, oa)
        if not papers and not grants:
            continue 
        score = score_pi(gp, len(papers), len(grants))
        if priors is not None:
            score = round(min(score * priors.score_multiplier(
                gp.pi.author_id.rsplit("/", 1)[-1], gp.pi.institution, gp.pi.area), 1.0), 3)
        staged.append((gp, papers, grants, score, assign_tier(score)))

    why_by_id = write_why_match_batch(
        [(gp, papers, grants) for gp, papers, grants, _, _ in staged],
        student_summary, llm,
    )

    supervisors = []
    for gp, papers, grants, score, tier in staged:
        sid = gp.pi.author_id.rsplit("/", 1)[-1]
        why = why_by_id.get(sid) or _why_fallback(gp.pi, papers)
        supervisors.append(to_supervisor(gp, papers, grants, [], score, tier, why))

    supervisors.sort(key=lambda s: s.score, reverse=True)

    meta = ShortlistMeta(
        student_id=str(profile.get("student_id", "unknown")),
        generated_at=datetime.now(timezone.utc).isoformat(),
        target_countries=target_countries,
        stated_areas=[aq.area for aq in area_queries],
        total_candidates_retrieved=n_retrieved,
        total_after_filters=len(supervisors),
        llm_provider=llm.provider,
    )
    return Shortlist(meta=meta, supervisors=supervisors)


def _student_summary(profile: dict) -> str:
    bits = []
    if profile.get("education_history"):
        last = profile["education_history"][-1]
        bits.append(f"{last.get('degree','')} at {last.get('institution','')}")
    if profile.get("research_interests"):
        bits.append("interests: " + ", ".join(profile["research_interests"]))
    if profile.get("intro_call_summary"):
        bits.append(profile["intro_call_summary"][:300])
    return " | ".join(bits)
