from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from uuid import UUID
from typing import List

from ..db import get_db
from .. import models, schemas
from ..scoring import compute_subscores, total_score
from ..suggestions import generate_suggestions

router = APIRouter(prefix="/match", tags=["match"])

@router.post("/{job_id}/run", response_model=schemas.MatchRunOut)
def run_match(job_id: UUID, db: Session = Depends(get_db)):
    job = db.get(models.Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")

    run = models.MatchRun(job_id=job_id)
    db.add(run)
    db.commit()
    db.refresh(run)

    # compute over all candidates with a CV document
    candidates = db.query(models.Candidate).all()

    # Collect candidate latest CV text
    candidate_docs = {
        c.id: (db.query(models.Document).filter(models.Document.candidate_id == c.id, models.Document.type == 'cv')
                        .order_by(models.Document.uploaded_at.desc()).first())
        for c in candidates
    }

    # First pass: compute scores
    results = []
    jd_payload = {
        "title": job.title,
        "jd_skills": job.jd_skills,
        "jd_required_skills": job.jd_required_skills,
        "jd_preferred_skills": job.jd_preferred_skills,
    }

    for c in candidates:
        doc = candidate_docs.get(c.id)
        if not doc:
            continue
        subs, blockers = compute_subscores(jd_payload, doc.text_extracted or "")
        score = total_score(subs, blockers)
        results.append({
            "candidate_id": str(c.id),
            "total_score": score,
            "subscores": subs.to_dict(),
            "hard_blockers": blockers,
            "doc": doc,  # keep for suggestions
        })

    # Rank
    results.sort(key=lambda r: r["total_score"], reverse=True)
    for idx, r in enumerate(results, start=1):
        r["rank"] = idx

    # Determine Top-5 threshold
    threshold = results[4]["total_score"] if len(results) >= 5 else (results[-1]["total_score"] if results else 0.0)

    # Suggestions
    enriched = []
    for r in results:
        sugg = generate_suggestions(jd_payload, r["doc"].text_extracted or "", r["subscores"], threshold, r["total_score"])
        enriched.append(models.MatchScore(
            run_id=run.id,
            candidate_id=r["candidate_id"],
            total_score=r["total_score"],
            subscores=r["subscores"],
            hard_blockers=r["hard_blockers"],
            rank=r["rank"],
            suggestions=sugg,
        ))

    for row in enriched:
        db.add(row)
    db.commit()

    return run

@router.get("/{run_id}/results", response_model=schemas.RunResultsOut)
def get_results(run_id: UUID, top_n: int = Query(5, ge=1, le=100), db: Session = Depends(get_db)):
    run = db.get(models.MatchRun, run_id)
    if not run:
        raise HTTPException(404, "Run not found")

    rows: List[models.MatchScore] = (
        db.query(models.MatchScore)
        .filter(models.MatchScore.run_id == run_id)
        .order_by(models.MatchScore.rank.asc())
        .limit(top_n)
        .all()
    )

    results = [
        schemas.MatchScoreOut(
            candidate_id=row.candidate_id,
            total_score=row.total_score,
            subscores=row.subscores,
            hard_blockers=row.hard_blockers or [],
            rank=row.rank,
            suggestions=row.suggestions or {},
        )
        for row in rows
    ]

    return schemas.RunResultsOut(run_id=run.id, job_id=run.job_id, results=results)
