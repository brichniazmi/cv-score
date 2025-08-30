from dataclasses import dataclass
from typing import List, Dict, Tuple, Any, Set
import re

WEIGHTS = {
    "req_skills": 0.35,
    "pref_skills": 0.15,
    "role_relevance": 0.15,
    "experience_level": 0.10,
    "achievement_density": 0.10,
    "education": 0.05,
    "languages": 0.05,
    "continuity": 0.05,
}

@dataclass
class Subscores:
    req_skills: float = 0.0
    pref_skills: float = 0.0
    role_relevance: float = 0.0
    experience_level: float = 0.0
    achievement_density: float = 0.0
    education: float = 0.0
    languages: float = 0.0
    continuity: float = 1.0

    def to_dict(self):
        return {k: getattr(self, k) for k in WEIGHTS.keys()}

ROLE_KEYWORDS = {
    "data engineer": ["data pipeline", "etl", "airflow", "spark", "databricks", "delta lake"],
    "site reliability engineer": ["sre", "reliability", "incident", "slo", "kubernetes", "prometheus"],
}

SKILL_PATTERN = re.compile(r"[a-zA-Z][a-zA-Z0-9+.#-]{1,}\b")
BULLET_CHARS = {"•", "◦", "-", "—", "–", "*"}

# very small stopword list to filter JD tokens
STOPWORDS = {
    "the","and","with","for","to","of","in","on","as","a","an","is","are","will","be","by","or","you",
    "we","our","your","role","job","team","work","working","experience","years","year","responsibilities",
    "requirements","skills","preferred","required","plus","nice","have","ability","knowledge","strong","good",
    "excellent","communication","problem","solving","etc","including","such","that","this","these","those",
    "using","use","based","build","built","design","develop","developed","maintain","maintained","support",
    "manage","managed","lead","led","senior","junior","engineer","developer","analyst","manager","degree",
}

def extract_keywords(text: str) -> List[str]:
    tokens = [t.lower() for t in SKILL_PATTERN.findall(text or "")]
    uniq = []
    for t in tokens:
        if t not in uniq:
            uniq.append(t)
    return uniq

def jaccard(a: List[str], b: List[str]) -> float:
    A, B = set(a), set(b)
    if not A or not B:
        return 0.0
    return len(A & B) / len(A | B)

def _clean_line(line: str) -> str:
    s = (line or "").strip()
    while s and (s[0] in BULLET_CHARS):
        s = s[1:].lstrip()
    return s

def compute_subscores(jd: dict, cv_text: str) -> Tuple[Subscores, List[str]]:
    subs = Subscores()
    hard_blockers: List[str] = []

    cv_kw = extract_keywords(cv_text)

    req = [s.lower() for s in (jd.get("jd_required_skills") or jd.get("jd_skills") or [])]
    pref = [s.lower() for s in (jd.get("jd_preferred_skills") or [])]

    if req:
        present = sum(1 for r in req if r in cv_kw)
        subs.req_skills = present / len(req)
    if pref:
        present = sum(1 for p in pref if p in cv_kw)
        subs.pref_skills = present / len(pref)

    title = (jd.get("title") or "").lower()
    role_keys = ROLE_KEYWORDS.get(title, [])
    subs.role_relevance = jaccard(role_keys, cv_kw)

    lines = [l.strip() for l in (cv_text or "").splitlines() if l.strip()]
    num_bullets = sum(1 for l in lines if l[:1] in BULLET_CHARS)
    num_quant = sum(1 for l in lines if re.search(r"(\d+%|\d+[kmb]?|\bpercent\b)", l, flags=re.I))
    subs.achievement_density = min(1.0, (num_quant / max(1, num_bullets))) if num_bullets else 0.3

    subs.education = 0.5
    subs.languages = 0.5

    for must in jd.get("mandatory_certs", []) or []:
        if must.lower() not in cv_kw:
            hard_blockers.append(f"Missing mandatory cert: {must}")

    return subs, hard_blockers

def total_score(subs: Subscores, hard_blockers: List[str]) -> float:
    raw = sum(getattr(subs, k) * w for k, w in WEIGHTS.items())
    cap = 0.60 if hard_blockers else 1.00
    return min(raw, cap)

# ---------- New: Missing skills + humanized suggestions ----------
def _humanize_rewrite(line: str) -> str:
    return f"{line} — add a measurable outcome (e.g., “reduced cost by 30%”, “handled 200 tickets/month”)."

def infer_missing_skills(jd_text: str, cv_text: str, limit: int = 20) -> List[str]:
    jd_tokens = [t for t in extract_keywords(jd_text) if t not in STOPWORDS]
    cv_tokens = set(extract_keywords(cv_text))
    missing = [t for t in jd_tokens if (t not in cv_tokens)]
    # keep order but unique
    seen = set()
    cleaned = []
    for t in missing:
        if len(t) <= 2 and t.isalpha():
            continue
        if t in seen:
            continue
        seen.add(t)
        cleaned.append(t)
        if len(cleaned) >= limit:
            break
    return cleaned

def make_suggestions(jd: dict, cv_text: str) -> Dict[str, Any]:
    tokens: Set[str] = set(extract_keywords(cv_text))
    req = [(s or "").lower().strip() for s in (jd.get("jd_required_skills") or jd.get("jd_skills") or [])]
    pref = [(s or "").lower().strip() for s in (jd.get("jd_preferred_skills") or [])]

    jd_text = jd.get("jd_text") or ""

    # 1) Missing skills (present in JD text, absent in CV)
    missing_skills = infer_missing_skills(jd_text, cv_text, limit=20)

    # 2) Preferred skills present in CV to surface
    skills_to_surface = [s for s in pref if s and s in tokens]
    skills_to_surface = list(dict.fromkeys(skills_to_surface))[:6]

    # 3) Pick up to 3 shortest non-trivial lines to rewrite
    lines = [_clean_line(l) for l in (cv_text or "").splitlines()]
    lines = [l for l in lines if len(l) > 12 and any(c.isalpha() for c in l)]
    weakest = sorted(lines, key=len)[:3]
    bullets_to_rewrite = [{"original": l, "rewrite": _humanize_rewrite(l)} for l in weakest]

    # 4) Estimate potential gains
    missing_req = [s for s in req if s and s not in tokens]
    changes = []
    if missing_req:
        changes.append({"label": "Mention required skills: " + ", ".join(missing_req[:5]), "delta": 0.05})
    if weakest:
        changes.append({"label": "Quantify 3 key bullets", "delta": 0.05})

    return {
        "missing_skills": missing_skills,          # <--- for the UI
        "skills_to_surface": skills_to_surface,
        "hard_blockers": [],
        "bullets_to_add": [],
        "bullets_to_rewrite": bullets_to_rewrite,
        "estimated_score_gain": {"by_change": changes},
        "delta_to_top5": 0,
    }
