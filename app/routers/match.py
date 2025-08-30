# app/routers/match.py
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from ..db import get_db
from ..models import Job, Candidate, Document, MatchRun
from ..scoring import compute_subscores, total_score, suggest_improvements

router = APIRouter(prefix="/match", tags=["match"])

def _job_to_scoring_dict(job: Job) -> Dict[str, Any]:
    return {
        "title": job.title or "",
        "jd_text": job.jd_text or "",
        "jd_required_skills": job.jd_required_skills or job.jd_skills or [],
        "jd_preferred_skills": job.jd_preferred_skills or [],
        "mandatory_certs": [],  # optional field
    }

def _candidate_cv_text(db: Session, cand_id) -> str:
    docs = db.query(Document).filter(Document.candidate_id == cand_id).all()
    parts = []
    for d in docs:
        if (d.type or "").lower() == "cv":
            if d.text_extracted:
                parts.append(d.text_extracted)
    return "\n".join(parts).strip()

@router.post("/{job_id}/run")
def run_match(job_id: str, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    jd = _job_to_scoring_dict(job)

    # Collect candidates that at least have a CV document
    cands = db.query(Candidate).all()

    results: List[Dict[str, Any]] = []
    for c in cands:
        cv_text = _candidate_cv_text(db, c.id)
        if not cv_text:
            continue

        subs, blockers = compute_subscores(jd, cv_text)
        score = total_score(subs, blockers)
        suggestions = suggest_improvements(jd, cv_text, subs, blockers)

        results.append({
            "candidate_id": str(c.id),
            "candidate_label": c.external_ref or None,
            "total_score": round(score, 6),
            "subscores": subs.to_dict(),
            "hard_blockers": blockers,
            "suggestions": suggestions,
        })

    # sort + rank
    results.sort(key=lambda r: r["total_score"], reverse=True)
    for i, r in enumerate(results, start=1):
        r["rank"] = i
        # optional delta to top-5
        if i > 5 and results[4]["total_score"] > 0:
            r["suggestions"]["delta_to_top5"] = max(0.0, results[4]["total_score"] - r["total_score"])

    # persist to MatchRun.results_json
    run = MatchRun(job_id=job.id, results_json=results)
    db.add(run)
    db.commit()
    return {"id": str(run.id)}

@router.get("/{run_id}/results")
def get_results(run_id: str, top_n: int = Query(0, ge=0), db: Session = Depends(get_db)):
    run = db.get(MatchRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    res = run.results_json or []
    if top_n and top_n > 0:
        res = res[:top_n]
    return {"results": res}
