from typing import Dict, List
import re

SCORE_IMPACT = {
    "quantify_achievements": 0.05,
    "surface_missing_req_skills": 0.04,
    "explicit_tools": 0.02,
}

def generate_suggestions(jd: dict, cv_text: str, subscores: Dict[str, float], threshold: float, current: float) -> dict:
    suggestions = {
        "bullets_to_add": [],
        "bullets_to_rewrite": [],
        "skills_to_surface": [],
        "hard_blockers": [],
        "estimated_score_gain": {"by_change": []},
    }

    # Missing required skills
    req = [s.lower() for s in (jd.get("jd_required_skills") or jd.get("jd_skills") or [])]
    cv_kw = set(t.lower() for t in re.findall(r"[a-zA-Z][a-zA-Z0-9+.#-]{1,}\b", cv_text or ""))

    missing = [r for r in req if r not in cv_kw]
    if missing:
        suggestions["skills_to_surface"] = missing[:5]
        suggestions["estimated_score_gain"]["by_change"].append({
            "label": f"Mention required skills: {', '.join(missing[:5])}",
            "delta": SCORE_IMPACT["surface_missing_req_skills"],
        })

    # Quantify achievements
    lines = [l.strip() for l in (cv_text or "").splitlines() if l.strip()]
    weak = [l for l in lines if (l.startswith("-") or l.startswith("•")) and not re.search(r"(\d+%|\d+[kmb]?|\bpercent\b)", l, flags=re.I)]
    for w in weak[:3]:
        suggestions["bullets_to_rewrite"].append({
            "original": w,
            "rewrite": f"{w.rstrip('.')}; add a measurable outcome (e.g., 'reduced X by 30%' or 'handled N users/day').",
        })
    if weak:
        suggestions["estimated_score_gain"]["by_change"].append({
            "label": "Quantify 3 key bullets",
            "delta": SCORE_IMPACT["quantify_achievements"],
        })

    # Tool explicitness (simple heuristic)
    tools = ["airflow", "spark", "kubernetes", "terraform", "postgres", "aws", "azure"]
    used_but_hidden = [t for t in tools if any(t in l.lower() for l in lines) and t not in cv_kw]
    if used_but_hidden:
        suggestions["bullets_to_add"].append(
            f"Surface tools explicitly in bullets: {', '.join(used_but_hidden[:5])}"
        )
        suggestions["estimated_score_gain"]["by_change"].append({
            "label": "Name critical tools in bullets",
            "delta": SCORE_IMPACT["explicit_tools"],
        })

    # Distance to threshold (for UI)
    suggestions["delta_to_top5"] = max(0.0, threshold - current)
    return suggestions
