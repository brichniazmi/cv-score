from typing import List, Optional, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field

# Job
class JobCreate(BaseModel):
    title: str
    department: Optional[str] = None
    location: Optional[str] = None
    jd_text: str
    jd_skills: Optional[List[str]] = None
    jd_required_skills: Optional[List[str]] = None
    jd_preferred_skills: Optional[List[str]] = None

class JobOut(BaseModel):
    id: UUID
    title: str
    department: Optional[str]
    location: Optional[str]
    jd_text: str
    jd_skills: Optional[List[str]]
    jd_required_skills: Optional[List[str]]
    jd_preferred_skills: Optional[List[str]]

    class Config:
        from_attributes = True

# Candidate & Document
class CandidateCreate(BaseModel):
    external_ref: Optional[str] = None
    anonymized: bool = False

class CandidateOut(BaseModel):
    id: UUID
    external_ref: Optional[str]
    anonymized: bool

    class Config:
        from_attributes = True

class DocumentCreate(BaseModel):
    type: str = Field(pattern=r"^(cv|cover|other)$")
    text_extracted: str
    parsed_json: Optional[Dict[str, Any]] = None

class DocumentOut(BaseModel):
    id: UUID
    candidate_id: UUID
    type: str
    text_extracted: str
    parsed_json: Optional[Dict[str, Any]]

    class Config:
        from_attributes = True

# Match
class MatchRunOut(BaseModel):
    id: UUID
    job_id: UUID

    class Config:
        from_attributes = True

class MatchScoreOut(BaseModel):
    candidate_id: UUID
    total_score: float
    subscores: Dict[str, float]
    hard_blockers: List[str]
    rank: int
    suggestions: dict

class RunResultsOut(BaseModel):
    run_id: UUID
    job_id: UUID
    results: List[MatchScoreOut]
