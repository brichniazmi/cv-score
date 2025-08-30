# app/scoring.py
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional
import os
import re

# -------- Optional semantic embeddings (auto-fallback if not available) --------
_MODEL = None
_USE_EMBEDDINGS = True
try:
    use_env = os.getenv("AI_EMBEDDINGS", "auto").lower()
    if use_env in ("0", "false", "off"):
        raise ImportError("Embeddings disabled via AI_EMBEDDINGS")
    from sentence_transformers import SentenceTransformer, util  # type: ignore
    _MODEL = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
except Exception:
    _USE_EMBEDDINGS = False
    _MODEL = None

def _embed(texts: List[str]):
    if _MODEL is None:
        return None
    return _MODEL.encode(texts, normalize_embeddings=True)

def _cosine(a, b) -> float:
    if a is None or b is None or _MODEL is None:
        return 0.0
    # sentence-transformers util is fastest if present
    try:
        from sentence_transformers import util  # type: ignore
        import numpy as np  # type: ignore
        va = a.reshape(1, -1) if hasattr(a, "reshape") else np.array(a).reshape(1, -1)
        vb = b.reshape(1, -1) if hasattr(b, "reshape") else np.array(b).reshape(1, -1)
        return float(util.cos_sim(va, vb)[0][0])
    except Exception:
        return 0.0

# -------- Weights and score container (kept compatible) --------
WEIGHTS = {
    "req_skills": 0.40,          # ↑ a bit: we care more about requirements
    "pref_skills": 0.10,
    "role_relevance": 0.25,      # semantic similarity JD↔CV
    "experience_level": 0.10,
    "achievement_density": 0.07,
    "education": 0.04,
    "languages": 0.02,
    "continuity": 0.02,
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

# -------- Light NLP helpers (language-agnostic but tuned for EN JDs/CVs) --------
STOP = {
    "and","or","for","with","to","of","in","on","at","by","as","the","a","an","is","are",
    "be","you","we","our","your","will","this","that","from","about","etc","ie","eg",
    "within","across","using","use","hands-on","experience","experiences","year","years",
    "plus","+","prior","work","working","ability","abilityto","strong","excellent","good",
    "familiar","familiarity","understanding","knowledge","proven","track","record",
    "must","have","nice","need","needed","required","preferred","responsibilities",
    "requirements","qualification","qualifications","skills","skill","competencies",
    "role","position","candidate","cv","resume","job","description"
}

SKILL_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9+.#/-]{1,}", re.U)
BULLET = re.compile(r"^\s*(?:[-*•]|\d+\.)\s+", re.U | re.M)
HAS_NUMBER = re.compile(r"(\b\d+(\.\d+)?\b|\d+%|\bpercent\b)", re.I)

SYNONYMS = {
    "ms 365": "microsoft 365",
    "m365": "microsoft 365",
    "office 365": "microsoft 365",
    "powerbi": "power bi",
    "postgres": "postgresql",
    "postgre": "postgresql",
    "py": "python",
    "js": "javascript",
    "nodejs": "node.js",
    "node": "node.js",
    "ci/cd": "ci-cd",
    "machine-learning": "ml",
    "nlp": "natural language processing",
}

def _norm_token(t: str) -> str:
    s = t.strip().lower()
    s = SYNONYMS.get(s, s)
    return s

def extract_tokens(text: str) -> List[str]:
    toks = []
    for m in SKILL_TOKEN.findall(text or ""):
        s = _norm_token(m)
        if len(s) < 2: 
            continue
        if s in STOP:
            continue
        toks.append(s)
    # de-dup but keep order
    seen, out = set(), []
    for t in toks:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out

def extract_bullets(text: str) -> List[str]:
    # split by bullet markers, keep lines that look like items
    lines = [l.strip() for l in (text or "").splitlines()]
    out = []
    cur = []
    for ln in lines:
        if BULLET.match(ln):
            if cur:
                out.append(" ".join(cur).strip())
                cur = []
            out.append(BULLET.sub("", ln).strip())
        else:
            # attach continuation lines to last bullet-like chunk
            if out and ln and not ln.endswith(":"):
                out[-1] = (out[-1] + " " + ln).strip()
            elif ln.endswith(":"):
                # section header – start fresh
                if cur:
                    out.append(" ".join(cur).strip())
                    cur = []
            else:
                cur.append(ln)
    if cur:
        out.append(" ".join(cur).strip())
    # filter very short noise
    return [b for b in out if len(b) >= 4]

def _semantic_contains(cv_tokens: List[str], req: str, embs_cache: Dict[str, any]) -> bool:
    """Return True if CV appears to cover `req` token semantically."""
    req_n = _norm_token(req)
    if req_n in cv_tokens:
        return True
    if not _USE_EMBEDDINGS:
        return False
    # semantic check via embeddings (threshold tuned for MiniLM)
    # cache embeddings per token to avoid recompute
    if "cv_vecs" not in embs_cache:
        embs_cache["cv_vecs"] = _embed(cv_tokens) if cv_tokens else None
    if "req_vecs" not in embs_cache:
        embs_cache["req_vecs"] = {}
    if req_n not in embs_cache["req_vecs"]:
        embs_cache["req_vecs"][req_n] = _embed([req_n])[0] if _embed([req_n]) is not None else None
    q = embs_cache["req_vecs"][req_n]
    V = embs_cache["cv_vecs"]
    if q is None or V is None:
        return False
    # compute best cosine vs each cv token
    try:
        from sentence_transformers import util  # type: ignore
        import numpy as np  # type: ignore
        qv = q.reshape(1, -1) if hasattr(q, "reshape") else np.array(q).reshape(1, -1)
        sims = util.cos_sim(qv, V)[0]
        best = float(sims.max()) if hasattr(sims, "max") else 0.0
        return best >= 0.60
    except Exception:
        return False

def _jd_requirements(jd_text: str) -> Dict[str, List[str]]:
    """Extract required vs preferred-ish tokens from a JD text."""
    text = jd_text or ""
    tokens = extract_tokens(text)

    # naive sectioning
    lower = text.lower()
    req_section = []
    pref_section = []

    # try to find segments after typical headers
    def _slice_after(marker: str) -> str:
        i = lower.find(marker)
        return text[i:] if i >= 0 else ""

    req_text = (
        _slice_after("requirements") or
        _slice_after("must have") or
        _slice_after("what you'll need") or
        _slice_after("what you’ll need") or
        ""
    )
    pref_text = (
        _slice_after("nice to have") or
        _slice_after("preferred") or
        _slice_after("bonus") or
        _slice_after("good to have") or
        ""
    )

    req_section = extract_tokens(req_text) or tokens
    pref_section = extract_tokens(pref_text)

    # keep top-N distinct tokens, biasing toward tech-like forms
    def _score_tok(t: str) -> int:
        sc = 0
        if any(ch.isdigit() for ch in t): sc += 2
        if any(ch in "+#./-" for ch in t): sc += 2
        if len(t) >= 4: sc += 1
        return sc

    req_sorted = sorted(list(dict.fromkeys(req_section)), key=_score_tok, reverse=True)[:40]
    pref_sorted = sorted(list(dict.fromkeys(pref_section)), key=_score_tok, reverse=True)[:30]

    return {"required": req_sorted, "preferred": pref_sorted}

# -------- Main scoring functions (public API stays compatible) --------
def compute_subscores(jd: dict, cv_text: str) -> Tuple[Subscores, List[str]]:
    """
    jd: expects keys 'title', 'jd_text', 'jd_required_skills' (optional), 'jd_preferred_skills' (optional)
    """
    subs = Subscores()
    hard_blockers: List[str] = []
    embs_cache: Dict[str, any] = {}

    jd_text = (jd.get("jd_text") or "").strip()
    title = (jd.get("title") or "").strip()

    # Extract JD requirements (prefer explicit lists if present, else parse from JD text)
    jd_req = [(s or "").strip().lower() for s in (jd.get("jd_required_skills") or []) if s]
    jd_pref = [(s or "").strip().lower() for s in (jd.get("jd_preferred_skills") or []) if s]
    if not jd_req and jd_text:
        parsed = _jd_requirements(jd_text)
        jd_req = parsed["required"]
        jd_pref = jd_pref or parsed["preferred"]

    # CV tokens + bullets
    cv_tokens = extract_tokens(cv_text or "")
    bullets = extract_bullets(cv_text or "")

    # --- req/pref coverage with semantic fallback ---
    if jd_req:
        covered = sum(1 for r in jd_req if _semantic_contains(cv_tokens, r, embs_cache))
        subs.req_skills = covered / max(1, len(jd_req))
    if jd_pref:
        covered = sum(1 for p in jd_pref if _semantic_contains(cv_tokens, p, embs_cache))
        subs.pref_skills = covered / max(1, len(jd_pref))

    # --- role relevance (semantic JD summary vs CV) ---
    if _USE_EMBEDDINGS and _MODEL is not None:
        jd_sum = (title + ". " if title else "") + (jd_text[:1200] if jd_text else "")
        V = _embed([jd_sum, cv_text[:4000]])
        subs.role_relevance = _cosine(V[0], V[1])
    else:
        # cheap fallback: jaccard over tokens
        def jaccard(a: List[str], b: List[str]) -> float:
            A, B = set(a), set(b)
            return len(A & B) / len(A | B) if A and B else 0.0
        subs.role_relevance = jaccard(extract_tokens(title + " " + jd_text), cv_tokens)

    # --- experience level heuristic ---
    cv_low = (cv_text or "").lower()
    if re.search(r"\b(senior|lead|staff|principal)\b", cv_low):
        subs.experience_level = 0.8
    elif re.search(r"\b(mid|intermediate)\b", cv_low):
        subs.experience_level = 0.6
    elif re.search(r"\b(junior|entry)\b", cv_low):
        subs.experience_level = 0.4
    else:
        subs.experience_level = 0.5

    # --- achievement density: how many bullets have numbers/impact ---
    if bullets:
        num_bullets = len(bullets)
        quantified = sum(1 for b in bullets if HAS_NUMBER.search(b))
        subs.achievement_density = min(1.0, quantified / max(1, num_bullets))
    else:
        subs.achievement_density = 0.3

    # --- simple education/language presence ---
    edu_hit = re.search(r"\b(msc|bsc|phd|master|bachelor|degree|licence|licentiate)\b", cv_low)
    subs.education = 0.7 if edu_hit else 0.4
    lang_hit = re.search(r"\b(english|french|german|spanish|arabic|portuguese|italian|dutch)\b", cv_low)
    subs.languages = 0.6 if lang_hit else 0.3

    subs.continuity = 1.0  # placeholder (timeline analysis can be added)

    # Hard blockers (example: explicit certs in JD)
    for cert in (jd.get("mandatory_certs") or []):
        norm = _norm_token(cert)
        if not _semantic_contains(cv_tokens, norm, embs_cache):
            hard_blockers.append(f"Missing mandatory cert: {cert}")

    return subs, hard_blockers

def total_score(subs: Subscores, hard_blockers: List[str]) -> float:
    raw = sum(getattr(subs, k) * w for k, w in WEIGHTS.items())
    cap = 0.60 if hard_blockers else 1.00
    return min(raw, cap)

# -------- Rich suggestions (used by match router if available) --------
def suggest_improvements(jd: dict, cv_text: str, subs: Subscores, hard_blockers: List[str]) -> Dict:
    jd_text = (jd.get("jd_text") or "")
    parsed = _jd_requirements(jd_text)
    req = parsed["required"]
    pref = parsed["preferred"]
    cv_tokens = extract_tokens(cv_text or "")
    embs_cache: Dict[str, any] = {}
    missing = [r for r in req if not _semantic_contains(cv_tokens, r, embs_cache)]

    # bullets to rewrite: up to 3 non-quantified bullets
    bullets = extract_bullets(cv_text or "")
    to_fix = [b for b in bullets if not HAS_NUMBER.search(b)][:3]
    bullets_rw = []
    for b in to_fix:
        # if a missing skill exists, nudge to mention one
        skill_hint = (missing[0] if missing else "a key technology or metric")
        rewrite = (
            f"{b.rstrip('.')}. Add a measurable outcome and mention {skill_hint} "
            f"(e.g., 'reduced X by 30%', 'built Y used by N users')."
        )
        bullets_rw.append({"original": b[:220], "rewrite": rewrite[:400]})

    # surface skills the CV has but might be buried (heuristic: rare tokens with digits/symbols)
    surface = [t for t in cv_tokens if any(ch.isdigit() or ch in "+#./-" for ch in t)][:6]

    est_gain = []
    if missing:
        est_gain.append({"label": f"Mention required skills: {', '.join(missing[:3])}", "delta": 0.06})
    if bullets_rw:
        est_gain.append({"label": f"Quantify {len(bullets_rw)} bullet(s)", "delta": 0.05})

    return {
        "missing_skills": missing[:10],
        "skills_to_surface": surface,
        "bullets_to_add": [],
        "bullets_to_rewrite": bullets_rw,
        "hard_blockers": hard_blockers,
        "estimated_score_gain": {"by_change": est_gain},
        "delta_to_top5": 0  # filled by router if needed
    }
