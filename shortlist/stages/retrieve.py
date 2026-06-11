from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from ..sources.openalex import OpenAlex
from .parse_profile import AreaQueries


@dataclass
class Candidate:
    author_id: str
    author_name: str
    area: str                 
    author_position: str     
    institution: str
    country: str
    work: dict                


def retrieve(area_queries: list[AreaQueries], target_countries: list[str], oa: OpenAlex, years_back: int = 6,) -> list[Candidate]:
    from_year = datetime.now(timezone.utc).year - years_back
    target_lc = {c.lower() for c in target_countries}
    candidates: list[Candidate] = []

    for aq in area_queries:
        for phrase in aq.phrases:
            works = oa.works_by_search_country(phrase, target_countries, from_year)
            for w in works:
                for a in w.get("authorships", []):
                    inst, country = _pick_in_country_affiliation(a, target_lc)
                    if country is None:
                        continue
                    author = a.get("author", {})
                    candidates.append(
                        Candidate(
                            author_id=author.get("id", ""),
                            author_name=author.get("display_name", ""),
                            area=aq.area,
                            author_position=a.get("author_position", "middle"),
                            institution=inst or "",
                            country=country,
                            work=w,
                        )
                    )
    return candidates


def _pick_in_country_affiliation(authorship: dict, target_lc: set[str]):
    for inst in authorship.get("institutions", []):
        code = (inst.get("country_code") or "").lower()
        if code in target_lc:
            return inst.get("display_name"), code.upper()
    return None, None
