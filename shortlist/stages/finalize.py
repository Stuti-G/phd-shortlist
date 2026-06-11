from __future__ import annotations

from datetime import datetime, timezone

from ..schema import (GrantEvidence, LinkedProgram, PaperEvidence, Supervisor, Tier)
from ..sources.llm import LLM
from ..sources.openalex import OpenAlex
from .domain_gate import GatedPI
from .resolve_pis import looks_like_fellowship

def _domain_terms(area: str) -> list[str]:
    base = [w.lower() for w in area.replace("-", " ").split() if len(w) > 3]
    return base

def rank_papers_by_relevance(papers, area: str):
    terms = _domain_terms(area)
    def hits(p):
        t = (p.title or "").lower()
        return sum(1 for term in terms if term in t)
    return sorted(papers, key=hits, reverse=True)

def build_evidence(gp: GatedPI, oa: OpenAlex, max_papers: int = 4, max_grants: int = 5) -> tuple[list[PaperEvidence], list[GrantEvidence]]:
    pi = gp.pi
    papers: list[PaperEvidence] = []
    seen_works = set()
    unique_works = []
    for w in pi.in_area_works:
        wid = w.get("id", "")
        if wid and wid in seen_works:
            continue
        seen_works.add(wid)
        unique_works.append(w)
    for w in unique_works[:max_papers]: 
        doi = w.get("doi")
        oa_id = w.get("id", "")
        url = doi or oa_id
        if not url:
            continue
        is_last = _is_last_author(w, pi.author_id)
        papers.append(
            PaperEvidence(
                title=w.get("title") or "(untitled)",
                year=w.get("publication_year"),
                doi=doi,
                openalex_id=oa_id,
                url=url,
                is_last_author=is_last,
            )
        )

    grants: list[GrantEvidence] = []
    seen_awards = set()
    for w in pi.in_area_works:
        if len(grants) >= max_grants:
            break
        for aw in w.get("awards", []) or []:
            if len(grants) >= max_grants:
                break
            aid = aw.get("id")
            if not aid or aid in seen_awards:
                continue
            seen_awards.add(aid)
            try:
                award = oa.award(aid)
            except Exception:
                continue
            title = award.get("display_name") or ""
            if not title.strip():
                continue  
            ftype = award.get("funding_type", "")
            if looks_like_fellowship(f"{title} {ftype}"):
                continue  
            funder = (award.get("funder") or {})
            grants.append(
                GrantEvidence(
                    title=title,
                    funder=funder.get("display_name"),
                    funder_country=_funder_country(funder),
                    award_id=award.get("funder_award_id"),
                    funding_type=ftype or None,
                    url=award.get("landing_page_url") or aid,
                )
            )
    return papers, grants


def _is_last_author(work: dict, author_id: str) -> bool:
    for a in work.get("authorships", []):
        if a.get("author", {}).get("id") == author_id:
            return a.get("author_position") == "last"
    return False


def _funder_country(funder: dict) -> str | None:
    return (funder.get("country_code") or "").upper() or None

_ELIG_SYS = (
    "Extract eligibility restrictions from a PhD vacancy ad. The applicant is an "
    "international (non-domestic) student. Return JSON: "
    "{\"international_eligible\": bool, \"note\": str}. "
    "If the ad says things like 'UK only', 'home fees only', 'EU residents', "
    "'citizens/permanent residents only', set international_eligible=false."
)


def eligibility_ok(ad_text: str, llm: LLM) -> tuple[bool, str]:
    if not ad_text:
        return True, "no ad text; not asserting a restriction"
    resp = llm.complete_json(_ELIG_SYS, ad_text[:4000])
    if not isinstance(resp, dict):
        return True, "eligibility unparseable; kept (no positive restriction found)"
    return bool(resp.get("international_eligible", True)), str(resp.get("note", ""))


def score_pi(gp: GatedPI, n_papers: int, n_grants: int) -> float:
    pi = gp.pi
    seniority = min(pi.works_count / 60.0, 1.0)
    years = [w.get("publication_year") for w in pi.in_area_works if w.get("publication_year")]
    recency = 0.0
    if years:
        gap = datetime.now(timezone.utc).year - max(years)
        recency = max(0.0, 1.0 - gap / 8.0)
    evidence = min((n_papers + 2 * n_grants) / 6.0, 1.0)
    return round(0.45 * seniority + 0.30 * recency + 0.25 * evidence, 3)


def assign_tier(score: float) -> Tier:
    if score >= 0.66:
        return Tier.target    
    if score >= 0.4:
        return Tier.reach     
    return Tier.safety

_WHY_SYS = (
    "Write a 2-3 sentence why_match for a student emailing a potential PhD supervisor. "
    "Reference SPECIFIC work by the supervisor (use the given paper/grant titles) and tie "
    "it to the student's profile. No generic praise, no flattery, no em-dashes. "
    "Plain, human, concrete. Return JSON: {\"why_match\": str}."
)

_WHY_BATCH_SYS = (
    "You write why_match blurbs for a student emailing potential PhD supervisors. You get "
    "the student profile and a NUMBERED LIST of supervisors with their specific work. For "
    "EACH, write 2-3 sentences. RULES: "
    "(1) Reference the supervisor's SPECIFIC given work by title. "
    "(2) Address the STUDENT in second person ('your interest in X'), never first person. "
    "(3) Do NOT claim the supervisor works on the student's exact topic unless their given "
    "work actually shows it. If the overlap is indirect (e.g. the PI does brain-injury "
    "rehab and the student does PTSD), state the link honestly as a potential connection "
    "('PTSD and TBI frequently co-occur in veterans'), do not imply they already study it. "
    "(4) No generic praise, no flattery, no em-dashes. Plain, human, concrete. "
    "Return JSON: {\"blurbs\": [{\"i\": int, \"why_match\": str}, ...]} one per index."
)

WHY_BATCH_SIZE = 15


def _why_fallback(pi, papers) -> str:
    return f"Works on {pi.area}; see {papers[0].title}." if papers else f"Active in {pi.area}."


def write_why_match_batch(items: list[tuple[GatedPI, list, list]], student_summary: str,
                          llm: LLM) -> dict[str, str]:
    out: dict[str, str] = {}
    batch_size = llm.batch_size(WHY_BATCH_SIZE) 
    for start in range(0, len(items), batch_size):
        chunk = items[start:start + batch_size]
        lines = []
        for i, (gp, papers, grants) in enumerate(chunk):
            ranked = rank_papers_by_relevance(papers, gp.pi.area)
            ev = "; ".join([p.title for p in ranked[:2]] + [g.title for g in grants[:1]])
            lines.append(f"[{i}] {gp.pi.name} ({gp.pi.institution}), area {gp.pi.area}. Work: {ev}")
        user = f"Student: {student_summary}\nSupervisors:\n" + "\n".join(lines)
        resp = llm.complete_json(_WHY_BATCH_SYS, user)

        blurbs = {}
        if isinstance(resp, dict) and isinstance(resp.get("blurbs"), list):
            for b in resp["blurbs"]:
                if isinstance(b, dict) and "i" in b:
                    blurbs[b["i"]] = b.get("why_match", "")

        for i, (gp, papers, grants) in enumerate(chunk):
            sid = gp.pi.author_id.rsplit("/", 1)[-1]
            text = blurbs.get(i) or _why_fallback(gp.pi, papers)
            out[sid] = str(text)
    return out


def write_why_match(gp: GatedPI, student_summary: str, papers, grants, llm: LLM) -> str:
    pi = gp.pi
    ev = "; ".join([p.title for p in papers[:3]] + [g.title for g in grants[:1]])
    user = (
        f"Student: {student_summary}\n"
        f"Supervisor: {pi.name} ({pi.institution}). Area overlap: {pi.area}.\n"
        f"Supervisor work: {ev}"
    )
    resp = llm.complete_json(_WHY_SYS, user)
    if isinstance(resp, dict) and resp.get("why_match"):
        return str(resp["why_match"])
    return f"Works on {pi.area}; see {papers[0].title}." if papers else f"Active in {pi.area}."


def to_supervisor(gp: GatedPI, papers, grants, programs, score, tier, why, email=None) -> Supervisor:
    pi = gp.pi
    return Supervisor(
        supervisor_id=pi.author_id.rsplit("/", 1)[-1],
        name=pi.name,
        institution=pi.institution,
        country=pi.country,
        contact_email=email,
        research_focus=", ".join(t.get("display_name", "") for t in pi.author_record.get("topics", [])[:5]),
        matched_area=pi.area,
        tier=tier,
        score=score,
        papers=papers,
        grants=grants,
        linked_programs=programs,
        why_match=why,
    )
