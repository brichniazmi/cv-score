from fastapi import FastAPI, Response
from fastapi.responses import HTMLResponse
from .db import Base, engine
from .routers import jobs, candidates, match

# Create tables at startup (simple demo behavior)
Base.metadata.create_all(bind=engine)

app = FastAPI(title="CV Score API", version="0.5.0")

# API routers
app.include_router(jobs.router)
app.include_router(candidates.router)
app.include_router(match.router)

# Health endpoints
@app.get("/")
def root():
    return {"service": "cv-score", "status": "ok"}

@app.head("/")
def root_head():
    # Render and other load balancers sometimes send HEAD; reply 200 instead of 405
    return Response(status_code=200)

# ---- Minimal web UI at /ui: JD only + upload many CVs, show best match + missing skills ----
UI_HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>CV Score – Match CVs to a Job</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <style>
    :root { font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; }
    body { max-width: 1000px; margin: 24px auto; padding: 0 12px; background:#fafafa; }
    h1 { margin: 0 0 8px; }
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
  </style>
</head>
<body>
  <h1>CV Score <span class="pill">upload CVs → get the best match</span></h1>
  <p class="muted">1) Paste the Job Description. 2) Upload CVs (PDF/DOCX or paste text). 3) Run the match. We'll show the best CV and the missing requirements to improve it.</p>

  <div class="card">
    <h2>1) Job Description</h2>
    <label>Job Description (paste full text)</label>
    <textarea id="job_text" placeholder="Paste the full job description here..."></textarea>
    <div style="margin-top:12px; display:flex; gap:8px;">
      <button onclick="saveJob()">Save Job</button>
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
          <button class="secondary" onclick="uploadFiles()">Upload selected files</button>
          <span id="files_status" class="muted"></span>
        </div>
        <div id="files_log" class="muted" style="margin-top:8px;"></div>
      </div>

      <div>
        <label>Or paste a CV (text)</label>
        <input id="cv_label" type="text" placeholder="Name or label (optional, e.g., Jane Doe)" />
        <textarea id="cv_text" placeholder="Paste CV text here (optional alternative to files)..."></textarea>
        <div style="margin-top:8px;">
          <button class="secondary" onclick="uploadTextCV()">Save pasted CV</button>
          <span id="cv_text_status" class="muted"></span>
        </div>
      </div>
    </div>

    <p class="muted" style="margin-top:8px;">We’ll automatically create candidates behind the scenes for each CV you upload.</p>
  </div>

  <div class="card">
    <h2>3) Match</h2>
    <div style="display:flex; gap:8px; align-items:center;">
      <button onclick="runMatch()">Run match for Job</button>
      <button class="secondary" onclick="getResults()">Show Top-5</button>
      <span id="run_status" class="muted"></span>
    </div>

    <div id="best" class="card best" style="display:none; margin-top:12px;">
      <h3 style="margin:0 0 8px;">Best match <span id="best_name"></span><span id="best_score" class="badge"></span></h3>
      <div><span class="muted">Missing requirements detected in this CV:</span></div>
      <div id="best_missing" style="margin-top:6px;"></div>
      <div style="margin-top:8px;"><span class="muted">Suggested improvements:</span></div>
      <div id="best_rewrites" style="margin-top:6px;"></div>
    </div>

    <div id="results" style="margin-top:12px;"></div>
  </div>

  <div class="card">
    <h2>Debug</h2>
    <div class="muted">
      Job ID: <span id="dbg_job"></span> • Run ID: <span id="dbg_run"></span> • Uploaded CVs this session: <span id="dbg_cvcount">0</span>
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

function titleFromJD(jdText) {
  const first = (jdText || "").split("\\n").map(x => x.trim()).filter(Boolean)[0] || "";
  return first.slice(0, 80) || "Untitled Job";
}

async function ensureJobSaved() {
  if (jobId) return true;
  const jd_text = document.getElementById("job_text").value || "";
  if (!jd_text.trim()) { setText("job_status", "Please paste the Job Description first.", false, true); return false; }
  return await saveJob();
}

async function saveJob() {
  const jd_text = document.getElementById("job_text").value || "";
  if (!jd_text.trim()) { setText("job_status", "Please paste the Job Description", false, true); return false; }
  setText("job_status", "Saving job…");
  const payload = {
    title: titleFromJD(jd_text),
    jd_text,
    jd_required_skills: [],   // UI no longer captures these explicitly
    jd_preferred_skills: []
  };
  const r = await fetch("/jobs/", { method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify(payload) });
  if (!r.ok) { setText("job_status", "Error saving job", false, true); return false; }
  const j = await r.json();
  jobId = j.id;
  setText("job_status", "Job saved ✓", true, false);
  setDbg();
  return true;
}

async function createCandidate(name) {
  const payload = { external_ref: name || null, anonymized: false };
  const r = await fetch("/candidates/", { method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify(payload) });
  if (!r.ok) throw new Error("Create candidate failed");
  return await r.json(); // {id, ...}
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
  }
}

/* Improved: show exact backend error (status + message) if match fails */
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
    return;
  }

  const j = await r.json();
  runId = j.id;
  setText("run_status", "Run created ✓", true, false);
  setDbg();
}

function esc(s){ return (s||"").replace(/</g,"&lt;").replace(/>/g,"&gt;"); }

function renderBestRow(row){
  const best = document.getElementById("best");
  const nameEl = document.getElementById("best_name");
  const scoreEl = document.getElementById("best_score");
  const missEl = document.getElementById("best_missing");
  const rewEl  = document.getElementById("best_rewrites");

  const name = row.candidate_label || row.candidate_id;
  const scorePct = (row.total_score * 100).toFixed(1) + "%";
  nameEl.textContent = "— " + name;
  scoreEl.textContent = scorePct;

  const sugg = row.suggestions || {};
  const missing = (sugg.missing_skills || []);
  missEl.innerHTML = (missing.length ? missing.map(s => `<span class="chip">${esc(s)}</span>`).join(" ") : "<span class='muted'>(none)</span>");

  const rewrites = (sugg.bullets_to_rewrite || []).map(o => {
    return `<div style="margin:.25rem 0"><div class="muted">• ${esc(o.original)}</div><div>↳ ${esc(o.rewrite)}</div></div>`;
  }).join("");
  rewEl.innerHTML = rewrites || "<span class='muted'>(none)</span>";

  best.style.display = "block";
}

async function getResults() {
  if (!runId) { setText("run_status", "Run the match first", false, true); return; }
  setText("run_status", "Fetching results…");
  const r = await fetch(`/match/${runId}/results?top_n=5`);
  if (!r.ok) { setText("run_status", "Error fetching results", false, true); return; }
  const j = await r.json();
  setText("run_status", "Top-5 loaded ✓", true, false);

  const arr = j.results || [];
  if (arr.length) renderBestRow(arr[0]);

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
</script>
</body>
</html>
"""

@app.get("/ui", response_class=HTMLResponse)
def ui_page():
    return UI_HTML
