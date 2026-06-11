from __future__ import annotations

from dataclasses import dataclass

from ..sources.openalex import OpenAlex
from .retrieve import Candidate

MIN_WORKS = 8           
MIN_CAREER_YEARS = 4    
FELLOWSHIP_HINTS = ("fellowship", "studentship", "f31", "f32", "msca", "doctoral")


@dataclass
class ResolvedPI:
    author_id: str
    name: str
    institution: str
    country: str
    area: str
    works_count: int
    author_record: dict
    in_area_works: list[dict]   


def resolve_pis(candidates: list[Candidate], oa: OpenAlex) -> list[ResolvedPI]:
    by_author: dict[str, list[Candidate]] = {}
    for c in candidates:
        if c.author_id:
            by_author.setdefault(c.author_id, []).append(c)

    resolved: list[ResolvedPI] = []
    for author_id, group in by_author.items():
        was_last = any(c.author_position == "last" for c in group)
        if not was_last:
            continue

        try:
            rec = oa.author(author_id)
        except Exception:
            continue  
        works_count = rec.get("works_count", 0)
        if works_count < MIN_WORKS:
            continue
        if _career_years(rec) < MIN_CAREER_YEARS:
            continue

        rep = group[0]
        resolved.append(
            ResolvedPI(
                author_id=author_id,
                name=rep.author_name,
                institution=rep.institution,
                country=rep.country,
                area=rep.area,
                works_count=works_count,
                author_record=rec,
                in_area_works=[c.work for c in group],
            )
        )
    return resolved


def _career_years(author_record: dict) -> int:
    years = [c["year"] for c in author_record.get("counts_by_year", []) if c.get("works_count")]
    if not years:
        return 0
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).year - min(years)


def looks_like_fellowship(text: str) -> bool:
    t = (text or "").lower()
    return any(h in t for h in FELLOWSHIP_HINTS)
