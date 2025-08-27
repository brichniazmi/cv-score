from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID

from ..db import get_db
from .. import models, schemas

router = APIRouter(prefix="/jobs", tags=["jobs"])

@router.post("/", response_model=schemas.JobOut)
def create_job(payload: schemas.JobCreate, db: Session = Depends(get_db)):
    job = models.Job(
        title=payload.title,
        department=payload.department,
        location=payload.location,
        jd_text=payload.jd_text,
        jd_skills=payload.jd_skills,
        jd_required_skills=payload.jd_required_skills,
        jd_preferred_skills=payload.jd_preferred_skills,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job

@router.get("/{job_id}", response_model=schemas.JobOut)
def get_job(job_id: UUID, db: Session = Depends(get_db)):
    job = db.get(models.Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job
