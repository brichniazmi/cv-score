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
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from uuid import UUID

from ..db import get_db
from .. import models, schemas
from ..extract import extract_pdf, extract_docx  # <-- NEW

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
    doc = models.Document(
        candidate_id=candidate_id,
        type=payload.type,
        storage_uri="inline:text",
        text_extracted=payload.text_extracted,
        parsed_json=payload.parsed_json,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc

# ---------- NEW: file upload endpoint (PDF/DOCX) ----------
@router.post("/{candidate_id}/upload", response_model=schemas.DocumentOut)
async def upload_cv(candidate_id: UUID, file: UploadFile = File(...), db: Session = Depends(get_db)):
    c = db.get(models.Candidate, candidate_id)
    if not c:
        raise HTTPException(404, "Candidate not found")

    name = (file.filename or "").lower()
    if not (name.endswith(".pdf") or name.endswith(".docx")):
        raise HTTPException(415, "Only .pdf or .docx files are supported")

    data = await file.read()
    if len(data) > 10 * 1024 * 1024:  # 10 MB cap
        raise HTTPException(413, "File too large (max 10 MB)")

    try:
        if name.endswith(".pdf"):
            text = extract_pdf(data)
        else:
            text = extract_docx(data)
    except Exception as e:
        raise HTTPException(400, f"Could not extract text: {e}")

    if not text.strip():
        raise HTTPException(422, "No text could be extracted from this file")

    doc = models.Document(
        candidate_id=candidate_id,
        type="cv",
        storage_uri=f"upload:{file.filename}",
        text_extracted=text,
        parsed_json=None,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc
