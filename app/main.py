from fastapi import FastAPI, Response
from fastapi.responses import HTMLResponse
from sqlalchemy import text
from .db import Base, engine
from .routers import jobs, candidates, match
 
# --- one-shot tiny migration to add results_json if missing on match_run ---
def ensure_results_column() -> None:
    with engine.begin() as conn:
        try:
            conn.execute(text(
                "ALTER TABLE match_run "
                "ADD COLUMN IF NOT EXISTS results_json JSONB "
                "DEFAULT '[]'::jsonb NOT NULL;"
            ))
        except Exception:
            try:
                conn.execute(text(
                    "ALTER TABLE match_run "
                    "ADD COLUMN results_json JSON NOT NULL DEFAULT '[]';"
                ))
            except Exception:
                pass

# Create tables, then ensure the column exists (idempotent)
Base.metadata.create_all(bind=engine)
ensure_results_column()

app = FastAPI(title="CV Score API", version="0.6.1")

# API routers
app.include_router(jobs.router)
app.include_router(candidates.router)
app.include_router(match.router)

# Health endpoints
@app.get("/")
def root():
    return {"service": "cv-score", "status": "ok", "version": "0.6.1"}

@app.head("/")
def root_head():
    # Render and other load balancers sometimes send HEAD; reply 200 instead of 405
    return Response(status_code=200)

# ---- Web UI at /ui: JD + multi-CV upload + AI-style narrative report ----
UI_HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>CV Score – Match CVs to a Job</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <style>
    :root { font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; }
    body { max-width: 1024px; margin: 24px auto; padding: 0 12px; background:#fafafa; color:#0f172a; }
    h1 { margin: 0 0 8px; }
    h2 { margin: 0 0 6px; }
    .card { border: 1px solid #e5e7eb; border-radius: 12px; padding: 16px; margin: 12px 0; background:#fff; }
    label { display:block; font-weight:600; margin: 10px 0 6px; }
    textarea, input[type=text] { width: 100%; padding: 10px; border: 1px solid #d1d5db; border-radius: 8px; background:#fff; }
    textarea { min-height: 140px; }
    button { padding: 10px 14px; border: 0; border-radius: 10px; background: #111827; color: #fff; cursor: pointer; }
    button.secondary { background:#4b5563; }
    .muted { color:#6b7280; font-size: 12px; }
    .ok { color: #065f46; }
    .err { color: #7f1d1d; }
    .pill { display:inline-block; background:#eef2ff; color:#3730a3; padding:4px 8px; border-radius:999px; font-size:12px; margin-left:8px;}
    .grid { display:grid; gap:12px; }
    .grid-2 { grid-template-columns: 1fr 1fr; }
    .chip { display:inline-block; padding:4px 10px; border-radius:999px; background:#f3f4f6; margin:2px; font-size:12px; }
    table { width: 100%; border-collapse: collapse; margin-top: 8px; }
    th, td { padding: 8px; border-bottom: 1px solid #eee; text-align: left; vertical-align: top; }
    pre { white-space: pre-wrap; word-break: break-word; }
    input[type=file]{margin-top:6px}
    .best { border:2px solid #60a5fa; }
    .badge { display:inline-block; background:#dcfce7; color:#166534; padding:2px 8px; border-radius:999px; font-size:12px; margin-left:6px; }
    .sect { margin-top:10px; }
    .sect h4 { margin: 0 0 6px; font-size: 14px; color:#111827; }
    .list { margin: 0; padding-left: 18px; }
    .list li { margin: 4px 0; }
    .kline { display:flex; flex-wrap:wrap; gap:6px; }
    .kline .chip { background:#eef2ff; color:#1e293b; }
    .code { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size:12px; color:#334155; }
  </style>
</head>
<body>
  <h1>CV Score <span class="pill">upload CVs → get the best match</span></h1>
  <p class="muted">1) Paste the Job Description. 2) Upload CVs (PDF/DOCX or paste text). 3) Run the match. You'll get an AI-style report for the best CV.</p>

  <div class="card">
    <h2>1) Job Description</h2>
    <label>Job Description (paste full text)</label>
    <textarea id="job_text" placeholder="Paste the full job description here..."></textarea>
    <div style="margin-top:12px; display:flex; gap:8px;">
      <button id="btn_save_job" type="button">Save Job</button>
      <span id="job_status" class="muted"></span>
    </div>
  </div>

  <div class="card">
    <h2>2) Upload CVs</h2>

    <div class="grid grid-2">
      <div>
        <label>Upload CV files (PDF or DOCX) – multiple allowed</label>
        <input id="cv_files" type="file" multiple
          accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" />
        <div style="margin-top:8px;">
          <button id="btn_upload_files" class="secondary" type="button">Upload selected files</button>
          <span id="files_status" class="muted"></span>
        </div>
        <div id="files_log" class="muted" style="margin-top:8px;"></div>
      </div>

      <div>
        <label>Or paste a CV (text)</label>
        <input id="cv_label" type="text" placeholder="Name or label (optional, e.g., Jane Doe)" />
        <textarea id="cv_text" placeholder="Paste CV text here (optional alternative to files)..."></textarea>
        <div style="margin-top:8px;">
          <button id="btn_upload_text_cv" class="secondary" type="button">Save pasted CV</button>
          <span id="cv_text_status" class="muted"></span>
        </div>
      </div>
    </div>

    <p class="muted" style="margin-top:8px;">We’ll automatically create candidates behind the scenes for each CV you upload.</p>
  </div>

  <div class="card">
    <h2>3) Match</h2>
    <div style="display:flex; gap:8px; align-items:center;">
      <button id="btn_run_match" type="button">Run match for Job</button>
      <button id="btn_get_results" class="secondary" type="button">Show Top-5</button>
      <span id="run_status" class="muted"></span>
    </div>

    <div id="best" class="card best" style="display:none; margin-top:12px;">
      <h3 style="margin:0 0 8px;">Best match <span id="best_name"></span><span id="best_score" class="badge"></span></h3>

      <div class="sect" id="quick_read">
        <h4>Quick read</h4>
        <ul class="list" id="quick_points"></ul>
      </div>

      <div class="sect">
        <h4>What’s missing (add if true)</h4>
        <div id="best_missing" class="kline"></div>
      </div>

      <div class="sect">
        <h4>How to tailor the CV</h4>
        <div id="best_rewrites"></div>
      </div>

      <div class="sect">
        <h4>Keyword checklist (ATS friendly)</h4>
        <div id="best_keywords" class="kline"></div>
      </div>

      <div class="sect">
        <h4>Summary of gaps</h4>
        <div id="best_summary" class="muted"></div>
      </div>
    </div>

    <div id="results" style="margin-top:12px;"></div>
  </div>

  <div class="card">
    <h2>Debug</h2>
    <div class="muted">
      Job ID: <span id="dbg_job"></span> • Run ID: <span id="dbg_run"></span> • Uploaded CVs this session: <span id="dbg_cvcount">0</span>
      • API: <span id="dbg_api"></span>
    </div>
  </div>

<script>
let jobId = null;
let runId = null;
let uploadedCount = 0;

function setText(id, txt, ok=false, err=false) {
  const el = document.getElementById(id);
  el.textContent = txt || "";
  el.className = ok ? "ok" : err ? "err" : "muted";
}
function setDbg() {
  document.getElementById("dbg_job").textContent = jobId || "—";
  document.getElementById("dbg_run").textContent = runId || "—";
  document.getElementById("dbg_cvcount").textContent = uploadedCount;
}
function esc(s){ return (s||"").replace(/</g,"&lt;").replace(/>/g,"&gt;"); }

function titleFromJD(jdText) {
  const first = (jdText || "").split("\\n").map(x => x.trim()).filter(Boolean)[0] || "";
  return first.slice(0, 80) || "Untitled Job";
}

async function pingApi(){
  try{
    const r = await fetch("/");
    const j = await r.json();
    document.getElementById("dbg_api").textContent = (j.status || "ok") + " v" + (j.version || "");
  }catch(e){
    document.getElementById("dbg_api").textContent = "unreachable";
    console.error("API ping failed", e);
  }
}

async function ensureJobSaved() {
  if (jobId) return true;
  const jd_text = document.getElementById("job_text").value || "";
  if (!jd_text.trim()) { setText("job_status", "Please paste the Job Description first.", false, true); return false; }
  return await saveJob();
}

async function saveJob() {
  try{
    const jd_text = document.getElementById("job_text").value || "";
    if (!jd_text.trim()) { setText("job_status", "Please paste the Job Description", false, true); return false; }
    setText("job_status", "Saving job…");
    const payload = {
      title: titleFromJD(jd_text),
      jd_text,
      jd_required_skills: [],
      jd_preferred_skills: []
    };
    const r = await fetch("/jobs/", { method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify(payload) });
    if (!r.ok) { setText("job_status", "Error saving job", false, true); console.error("saveJob failed", r.status, await r.text()); return false; }
    const j = await r.json();
    jobId = j.id;
    setText("job_status", "Job saved ✓", true, false);
    setDbg();
    return true;
  }catch(e){
    setText("job_status", "Error: " + (e.message || "failed"), false, true);
    console.error("saveJob error", e);
    return false;
  }
}

async function createCandidate(name) {
  const payload = { external_ref: name || null, anonymized: false };
  const r = await fetch("/candidates/", { method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify(payload) });
  if (!r.ok) { console.error("createCandidate failed", r.status, await r.text()); throw new Error("Create candidate failed"); }
  return await r.json();
}

async function uploadFiles() {
  const ok = await ensureJobSaved();
  if (!ok) return;
  const input = document.getElementById("cv_files");
  const files = Array.from(input.files || []);
  if (!files.length) { setText("files_status", "Choose one or more PDF/DOCX", false, true); return; }
  setText("files_status", "Uploading files…");
  const log = [];
  for (const file of files) {
    try {
      const label = (file.name || "cv").replace(/\\.(pdf|docx)$/i,"");
      const cand = await createCandidate(label);
      const form = new FormData();
      form.append("file", file);
      const r = await fetch(`/candidates/${cand.id}/upload`, { method:"POST", body: form });
      if (!r.ok) throw new Error(await r.text());
      uploadedCount += 1;
      log.push("✓ " + label);
    } catch (e) {
      log.push("✗ " + (file.name || "cv") + " — " + (e.message || "upload failed"));
      console.error("uploadFiles error", e);
    }
  }
  document.getElementById("files_log").innerHTML = log.map(x => "<div>"+x+"</div>").join("");
  setText("files_status", "Done", true, false);
  setDbg();
}

async function uploadTextCV() {
  const ok = await ensureJobSaved();
  if (!ok) return;
  const text = document.getElementById("cv_text").value || "";
  if (!text.trim()) { setText("cv_text_status", "Paste some CV text first", false, true); return; }
  setText("cv_text_status", "Saving CV…");
  const label = document.getElementById("cv_label").value || "Pasted CV";
  try {
    const cand = await createCandidate(label);
    const payload = { type: "cv", text_extracted: text, parsed_json: null };
    const r = await fetch(`/candidates/${cand.id}/documents`, { method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify(payload) });
    if (!r.ok) throw new Error(await r.text());
    uploadedCount += 1;
    setText("cv_text_status", "CV saved ✓", true, false);
    setDbg();
  } catch (e) {
    setText("cv_text_status", "Error: " + (e.message || "failed"), false, true);
    console.error("uploadTextCV error", e);
  }
}

async function runMatch() {
  const ok = await ensureJobSaved();
  if (!ok) return;

  if (uploadedCount === 0) {
    setText("run_status", "Upload at least one CV", false, true);
    return;
  }

  setText("run_status", "Running match…");
  let r;
  try {
    r = await fetch(`/match/${jobId}/run`, { method:"POST" });
  } catch (e) {
    setText("run_status", "Network error: " + (e.message || e), false, true);
    console.error("runMatch network error", e);
    return;
  }

  if (!r.ok) {
    let msg = "";
    try {
      const j = await r.json();
      msg = j.detail || JSON.stringify(j);
    } catch (_) {
      msg = await r.text();
    }
    setText("run_status", `Error running match (HTTP ${r.status}): ${msg}`, false, true);
    console.error("runMatch failed", r.status, msg);
    return;
  }

  const j = await r.json();
  runId = j.id;
  setText("run_status", "Run created ✓", true, false);
  setDbg();
}

function extractJDBullets(text) {
  const lines = (text || "").split("\\n").map(s => s.trim()).filter(Boolean);
  const bullets = [];
  for (const ln of lines) {
    if (/^(\\-|\\*|•|\\d+\\.)\\s+/u.test(ln)) bullets.push(ln.replace(/^(\\-|\\*|•|\\d+\\.)\\s+/u, ''));
  }
  if (!bullets.length) bullets.push(...lines.slice(0, 5));
  return bullets.slice(0, 6);
}

function buildKeywordChecklist(sugg) {
  const chips = [];
  const missing = (sugg.missing_skills || []).slice(0, 8);
  const surface = (sugg.skills_to_surface || []).slice(0, 6);
  for (const m of missing) chips.push(`<span class="chip">${esc(m)}</span>`);
  for (const s of surface) chips.push(`<span class="chip">${esc(s)}</span>`);
  const extra = ["appel d'offres","RFP","SLA","fournisseurs","sous-traitants","TCO","maintenance préventive","disponibilité"];
  for (const e of extra) {
    if (![...missing, ...surface].includes(e)) chips.push(`<span class="chip">${esc(e)}</span>`);
  }
  return chips.join(" ");
}

function renderBestNarrative(row){
  const best = document.getElementById("best");
  const nameEl = document.getElementById("best_name");
  const scoreEl = document.getElementById("best_score");

  const name = row.candidate_label || row.candidate_id;
  const scorePct = (row.total_score * 100).toFixed(1) + "%";
  nameEl.textContent = "— " + name;
  scoreEl.textContent = scorePct;

  const jd_text = document.getElementById("job_text").value || "";
  const quickList = document.getElementById("quick_points");
  quickList.innerHTML = "";
  const bullets = extractJDBullets(jd_text);
  const reqPct = row.subscores && typeof row.subscores.req_skills === "number"
    ? Math.round(row.subscores.req_skills * 100) : null;
  const relPct = row.subscores && typeof row.subscores.role_relevance === "number"
    ? Math.round(row.subscores.role_relevance * 100) : null;

  const qitems = [];
  qitems.push(`<li><strong>Role focus (JD):</strong> ${bullets.slice(0,3).map(esc).join("; ") || "—"}</li>`);
  qitems.push(`<li><strong>Candidate:</strong> ${esc(name)} — score <strong>${scorePct}</strong>${reqPct!=null?`, req-skill coverage ~${reqPct}%`:''}${relPct!=null?`, semantic relevance ~${relPct}%`:''}</li>`);
  quickList.innerHTML = qitems.join("");

  const missEl = document.getElementById("best_missing");
  const sugg = row.suggestions || {};
  const missing = (sugg.missing_skills || []);
  missEl.innerHTML = (missing.length ? missing.map(s => `<span class="chip">${esc(s)}</span>`).join(" ") : "<span class='muted'>(none)</span>");

  const rewEl  = document.getElementById("best_rewrites");
  const rewrites = (sugg.bullets_to_rewrite || []);
  if (rewrites.length) {
    rewEl.innerHTML = rewrites.map(o => {
      return `<div style="margin:.4rem 0">
        <div class="muted">• ${esc(o.original)}</div>
        <div>↳ ${esc(o.rewrite)}</div>
      </div>`;
    }).join("");
  } else {
    rewEl.innerHTML = "<span class='muted'>(none)</span>";
  }

  const kEl = document.getElementById("best_keywords");
  kEl.innerHTML = buildKeywordChecklist(sugg);

  const sumEl = document.getElementById("best_summary");
  const gaps = missing.slice(0,3).join(", ") || "no critical gaps detected";
  sumEl.innerHTML = `Main gaps: <span class="code">${esc(gaps)}</span>. Add the missing requirements (if true) and quantify 2–3 bullets to lift the score.`;

  best.style.display = "block";
}

function renderResultsTable(arr){
  const rows = arr.map(row => {
    const name = row.candidate_label || row.candidate_id;
    const scorePct = (row.total_score * 100).toFixed(1) + "%";
    const rank = (row.rank != null) ? row.rank : "-";
    const sugg = row.suggestions || {};
    const missing = (sugg.missing_skills || []).map(s => `<span class="chip">${esc(s)}</span>`).join(" ");
    return `<tr>
      <td>${esc(name)}<div class="muted"><code>${row.candidate_id}</code></div></td>
      <td>${scorePct}</td>
      <td>${rank}</td>
      <td>${missing || "<span class='muted'>(none)</span>"}</td>
    </tr>`;
  }).join("");
  document.getElementById("results").innerHTML =
    `<table><thead><tr><th>Candidate</th><th>Score</th><th>Rank</th><th>Missing requirements</th></tr></thead><tbody>` +
    (rows || "<tr><td colspan='4'>No results.</td></tr>") + "</tbody></table>";
}

async function getResults() {
  if (!runId) { setText("run_status", "Run the match first", false, true); return; }
  setText("run_status", "Fetching results…");
  const r = await fetch(`/match/${runId}/results?top_n=5`);
  if (!r.ok) { setText("run_status", "Error fetching results", false, true); console.error("getResults failed", r.status, await r.text()); return; }
  const j = await r.json();
  setText("run_status", "Top-5 loaded ✓", true, false);

  const arr = j.results || [];
  if (arr.length) renderBestNarrative(arr[0]);
  renderResultsTable(arr);
}

/* ---- Bind event listeners instead of inline onclick (CSP-safe) ---- */
window.addEventListener("DOMContentLoaded", () => {
  document.getElementById("btn_save_job")?.addEventListener("click", saveJob);
  document.getElementById("btn_upload_files")?.addEventListener("click", uploadFiles);
  document.getElementById("btn_upload_text_cv")?.addEventListener("click", uploadTextCV);
  document.getElementById("btn_run_match")?.addEventListener("click", runMatch);
  document.getElementById("btn_get_results")?.addEventListener("click", getResults);

  // health ping for quick diagnosis
  pingApi();
  setDbg();
});
</script>
</body>
</html>
"""

@app.get("/ui", response_class=HTMLResponse)
def ui_page():
    return UI_HTML
