from dataclasses import dataclass
from typing import List, Dict, Tuple
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

    subs.experience_level = 0.7 if any(y in cv_kw for y in ["senior", "lead", "5+", "6+", "7+"]) else 0.5

    lines = [l.strip() for l in (cv_text or "").splitlines() if l.strip()]
    num_bullets = sum(1 for l in lines if l.startswith("-") or l.startswith("•") or l.startswith("*"))
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
