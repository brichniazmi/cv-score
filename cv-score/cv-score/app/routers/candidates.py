from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID

from ..db import get_db
from .. import models, schemas

router = APIRouter(prefix="/candidates", tags=["candidates"])

@router.post("/", response_model=schemas.CandidateOut)
def create_candidate(payload: schemas.CandidateCreate, db: Session = Depends(get_db)):
    c = models.Candidate(external_ref=payload.external_ref, anonymized=payload.anonymized)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c

@router.post("/{candidate_id}/documents", response_model=schemas.DocumentOut)
def add_document(candidate_id: UUID, payload: schemas.DocumentCreate, db: Session = Depends(get_db)):
    c = db.get(models.Candidate, candidate_id)
    if not c:
        raise HTTPException(404, "Candidate not found")
    doc = models.Document(candidate_id=candidate_id, type=payload.type, storage_uri="inline:text", text_extracted=payload.text_extracted, parsed_json=payload.parsed_json)
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc
