from sqlalchemy import Column, String, Text, Boolean, Integer, Float, DateTime, ForeignKey, JSON, ARRAY
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from uuid import uuid4
from datetime import datetime

from .db import Base

class Job(Base):
    __tablename__ = "job"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    title = Column(String)
    department = Column(String)
    location = Column(String)
    jd_text = Column(Text)
    jd_skills = Column(ARRAY(String))
    jd_required_skills = Column(ARRAY(String))
    jd_preferred_skills = Column(ARRAY(String))
    created_at = Column(DateTime, default=datetime.utcnow)

    runs = relationship("MatchRun", back_populates="job")

class Candidate(Base):
    __tablename__ = "candidate"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    external_ref = Column(String)
    anonymized = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    documents = relationship("Document", back_populates="candidate")
    skills = relationship("CandidateSkill", back_populates="candidate")

class Document(Base):
    __tablename__ = "document"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    candidate_id = Column(UUID(as_uuid=True), ForeignKey("candidate.id"))
    type = Column(String)
    storage_uri = Column(String)
    text_extracted = Column(Text)
    parsed_json = Column(JSON)
    uploaded_at = Column(DateTime, default=datetime.utcnow)

    candidate = relationship("Candidate", back_populates="documents")

class CandidateSkill(Base):
    __tablename__ = "candidate_skill"
    candidate_id = Column(UUID(as_uuid=True), ForeignKey("candidate.id"), primary_key=True)
    canonical = Column(String, primary_key=True)
    skill_name = Column(String)
    months_experience = Column(Integer)
    last_used = Column(DateTime)
    confidence = Column(Float)

    candidate = relationship("Candidate", back_populates="skills")

class MatchRun(Base):
    __tablename__ = "match_run"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("job.id"))
    created_at = Column(DateTime, default=datetime.utcnow)

    # NEW: JSON storage for results used by the /match router
    results_json = Column(JSON, nullable=False, default=list)

    job = relationship("Job", back_populates="runs")
    scores = relationship("MatchScore", back_populates="run")

class MatchScore(Base):
    __tablename__ = "match_score"
    run_id = Column(UUID(as_uuid=True), ForeignKey("match_run.id"), primary_key=True)
    candidate_id = Column(UUID(as_uuid=True), ForeignKey("candidate.id"), primary_key=True)
    total_score = Column(Float)
    subscores = Column(JSON)
    hard_blockers = Column(ARRAY(String))
    rank = Column(Integer)
    suggestions = Column(JSON)

    run = relationship("MatchRun", back_populates="scores")
