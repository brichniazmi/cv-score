from typing import Tuple
from pypdf import PdfReader
from docx import Document as DocxDocument
import io

def extract_pdf(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    out = []
    for page in reader.pages:
        try:
            out.append(page.extract_text() or "")
        except Exception:
            continue
    return "\n".join(out).strip()

def extract_docx(data: bytes) -> str:
    doc = DocxDocument(io.BytesIO(data))
    paras = [p.text for p in doc.paragraphs]
    return "\n".join(paras).strip()
