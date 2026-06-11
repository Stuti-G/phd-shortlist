from __future__ import annotations

from dataclasses import dataclass, field

from ..sources.llm import LLM
from ..sources.openalex import OpenAlex

_SYS = (
    "You convert a student's stated research area into concise academic search phrases "
    "for a scholarly database. Return JSON: {\"phrases\": [str, ...]} with 2-4 phrases. "
    "Be specific and disambiguating — include discipline and, if the area implies one, "
    "the geographic or population context (e.g. 'Himalayan pilgrimage tourism' -> "
    "['religious tourism Himalaya', 'pilgrimage mobility South Asia']). No prose."
)


@dataclass
class AreaQueries:
    area: str                     
    phrases: list[str] = field(default_factory=list)


def parse_profile(profile: dict, oa: OpenAlex, llm: LLM) -> list[AreaQueries]:
    out: list[AreaQueries] = []
    for area in profile["research_interests"]:
        resp = llm.complete_json(_SYS, f"Stated area: {area}")
        phrases = (resp or {}).get("phrases") if isinstance(resp, dict) else None
        if not phrases:
            phrases = [area]
        out.append(AreaQueries(area=area, phrases=phrases))
    return out
