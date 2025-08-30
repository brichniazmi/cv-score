# app/routers/match.py
from __future__ import annotations
from typing import List, Dict, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..db import get_db
from .. import models
from .. import scoring

router = APIRouter(prefix="/match", tags=["match"])

def _best_cv_text_for_candidate(db: Session, candidate_id: UUID) -> str:
    # 1) Prefer uploaded CVs
    doc = (
        db.query(models.Document)
        .filter(
            models.Document.candidate_id == candidate_id,
            models.Document.type == "cv",
            models.Document.storage_uri.like("upload:%"),
        )
        .order_by(models.Document.id.desc())
        .first()
    )
    if doc and doc.text_extracted:
        return doc.text_extracted

    # 2) Fallback to any 'cv'
    doc = (
        db.query(models.Document)
        .filter(models.Document.candidate_id == candidate_id, models.Document.type == "cv")
        .order_by(models.Document.id.desc())
        .first()
    )
    if doc and doc.text_extracted:
        return doc.text_extracted

    # 3) Fallback to any document
    doc = (
        db.query(models.Document)
        .filter(models.Document.candidate_id == candidate_id)
        .order_by(models.Document.id.desc())
        .first()
    )
    return (doc.text_extracted or "") if doc else ""

def _job_to_dict(job: models.Job) -> Dict[str, Any]:
    return {
        "title": job.title,
        "jd_text": job.jd_text,
        "jd_required_skills": job.jd_required_skills or getattr(job, "jd_skills", []) or [],
        "jd_preferred_skills": job.jd_preferred_skills or [],
        "mandatory_certs": getattr(job, "mandatory_certs", []) or [],
    }

@router.post("/{job_id}/run")
def create_run(job_id: UUID, db: Session = Depends(get_db)) -> Dict[str, str]:
    job = db.get(models.Job, job_id)
    if not job:
        raise HTTPException(404, detail="Job not found")

    jd = _job_to_dict(job)

    candidates = db.query(models.Candidate).all()
    if not candidates:
        raise HTTPException(400, detail="No candidates exist. Upload at least one CV.")

    results: List[Dict[str, Any]] = []
    usable = 0

    for cand in candidates:
        cv_text = _best_cv_text_for_candidate(db, cand.id)
        if not (cv_text or "").strip():
            # Skip candidates with no usable text
            continue

        usable += 1
        subs, hard_blockers = scoring.compute_subscores(jd, cv_text)
        total = scoring.total_score(subs, hard_blockers)
        suggestions = scoring.make_suggestions(jd, cv_text)  # includes missing_skills

        results.append({
            "candidate_id": str(cand.id),
            "candidate_label": cand.external_ref or f"Candidate {str(cand.id)[:8]}",
            "total_score": round(total, 4),
            "subscores": {k: round(v, 4) for k, v in subs.to_dict().items()},
            "hard_blockers": hard_blockers,
            "suggestions": suggestions,
        })

    if usable == 0:
        raise HTTPException(400, detail="No usable CV text found. Make sure you uploaded a PDF/DOCX or pasted CV text.")

    results.sort(key=lambda r: r["total_score"], reverse=True)
    for i, r in enumerate(results, start=1):
        r["rank"] = i

    # Create run and store results on whichever column exists
    run = models.MatchRun(job_id=job_id)
    if hasattr(run, "results_json"):
        run.results_json = results
    elif hasattr(run, "results"):
        run.results = results
    else:
        raise HTTPException(500, detail="MatchRun model must have a 'results_json' or 'results' column to store results.")

    db.add(run)
    db.commit()
    db.refresh(run)
    return {"id": str(run.id)}

@router.get("/{run_id}/results")
def get_results(
    run_id: UUID,
    top_n: int = Query(5, ge=1, le=50),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    run = db.get(models.MatchRun, run_id)
    if not run:
        raise HTTPException(404, detail="Run not found")
    data = getattr(run, "results_json", None) or getattr(run, "results", None) or []
    return {"results": data[:top_n]}
