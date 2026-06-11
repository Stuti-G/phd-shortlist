from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Tier(str, Enum):
    reach = "reach"
    target = "target"
    safety = "safety"


class PaperEvidence(BaseModel):
    title: str
    year: Optional[int] = None
    doi: Optional[str] = None
    openalex_id: str
    url: str 
    is_last_author: bool = Field(
        ...,
        description="True if the PI is last/corresponding author — our main PI signal.",
    )


class GrantEvidence(BaseModel):
    title: str
    funder: Optional[str] = None
    funder_country: Optional[str] = None  
    award_id: Optional[str] = None
    funding_type: Optional[str] = None  
    url: Optional[str] = None


class LinkedProgram(BaseModel):
    title: str
    url: Optional[str] = None
    eligibility_note: Optional[str] = None  


class Supervisor(BaseModel):
    supervisor_id: str  
    name: str
    institution: str
    country: str  
    contact_email: Optional[str] = None 
    research_focus: str
    matched_area: str  
    tier: Optional[Tier] = None
    score: float  
    papers: list[PaperEvidence] = Field(default_factory=list)
    grants: list[GrantEvidence] = Field(default_factory=list)
    linked_programs: list[LinkedProgram] = Field(default_factory=list)

    why_match: str  


class ShortlistMeta(BaseModel):
    student_id: str
    generated_at: str
    target_countries: list[str]
    stated_areas: list[str]
    total_candidates_retrieved: int
    total_after_filters: int
    llm_provider: str
    pipeline_version: str = "0.1.0"


class Shortlist(BaseModel):
    meta: ShortlistMeta
    supervisors: list[Supervisor]
