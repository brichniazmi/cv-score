from fastapi import FastAPI, Response 
from fastapi.responses import HTMLResponse
from .db import Base, engine
from .routers import jobs, candidates, match

# Create tables at startup (simple demo behavior)
Base.metadata.create_all(bind=engine)

app = FastAPI(title="CV Score API", version="0.3.0")

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

# ---- Minimal web UI at /ui (JD only + CV upload) ----
UI_HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>CV Score – Simple UI</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <style>
    :root { font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; }
    body { max-width: 960px; margin: 24px auto; padding: 0 12px; }
    h1 { margin: 0 0 8px; }
    .card { border: 1px solid #ddd; border-radius: 12px; padding: 16px; margin: 12px 0; }
    label { display:block; font-weight:600; margin: 10px 0 6px; }
    textarea, input[type=text] { width: 100%; padding: 10px; border: 1px solid #ccc; border-radius: 8px; }
    textarea { min-height: 140px; }
    button { padding: 10px 14px; border: 0; border-radius: 10px; background: #111827; color: #fff; cursor: pointer; }
    button.secondary { background:#4b5563; }
    .muted { color:#6b7280; font-size: 12px; }
    .pill { display:inline-block; background:#eef2ff; color:#3730a3; padding:4px 8px; border-radius:999px; font-size:12px; margin-left:8px;}
    table { width: 100%; border-collapse: collapse; margin-top: 8px; }
    th, td { padding: 8px; border-bottom: 1px solid #eee; text-align: left; vertical-align: top; }
    .chip { display:inline-block; padding:3px 8px; border-radius:999px; background:#f3f4f6; margin:2px; font-size:12px; }
    .ok { color: #065f46; }
    .err { color: #7f1d1d; }
    pre { white-space: pre-wrap; word-break: break-word; }
    input[type=file]{margin-top:6px}
  </style>
</head>
<body>
  <h1>CV Score <span class="pill">simple</span></h1>
  <p class="muted">Paste a Job Description, create a Candidate, upload a CV (or paste text), run the match, and see missing skills + suggestions.</p>

  <div class="card">
    <h2>1) Job Description</h2>
    <label>Job Description (paste full text)</label>
    <textarea id="job_text" placeholder="Paste the full job description here..."></textarea>
    <div style="margin-top:12px; display:flex; gap:8px;">
      <button onclick="createJob()">Save Job</button>
      <span id="job_status" class="muted"></span>
    </div>
  </div>

  <div class="card">
    <h2>2) Candidate & CV</h2>
    <label>Candidate Name (shown in results)</label>
    <input id="cand_ref" type="text" placeholder="e.g., Jane Doe" />
    <div style="margin-top:8px;">
      <button onclick="createCandidate()">Create Candidate</button>
      <span id="cand_status" class="muted"></span>
    </div>

    <label style="margin-top:12px;">CV Text (optional)</label>
    <textarea id="cv_text" placeholder="Paste CV text here (optional if you upload a file)..."></textarea>
    <div style="margin-top:8px;">
      <button class="secondary" onclick="addCV()">Attach CV Text</button>
      <span id="cv_status" class="muted"></span>
    </div>

    <div style="margin-top:16px; padding-top:12px; border-top:1px dashed #ddd;">
      <label>Upload CV (PDF/DOCX)</label>
      <input id="cv_file" type="file"
        accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" />
      <div style="margin-top:8px;">
        <button class="secondary" onclick="uploadFile()">Upload file</button>
        <span id="file_status" class="muted"></span>
      </div>
      <p class="muted">Max 10 MB. Supported: .pdf, .docx</p>
    </div>
  </div>

  <div class="card">
    <h2>3) Match</h2>
    <div style="display:flex; gap:8px; align-items:center;">
      <button onclick="runMatch()">Run match for Job</button>
      <button class="secondary" onclick="getResults()">Show Top-5</button>
      <span id="run_status" class="muted"></span>
    </div>
    <div id="results"></div>
  </div>

  <div class="card">
    <h2>Debug</h2>
    <div class="muted">Job ID: <span id="dbg_job"></span> • Candidate ID: <span id="dbg_cand"></span> • Run ID: <span id="dbg_run"></span></div>
  </div>

<script>
let jobId = null;
let candidateId = null;
let runId = null;

function setText(id, txt, ok=false, err=false) {
  const el = document.getElementById(id);
  el.textContent = txt || "";
  el.className = ok ? "ok" : err ? "err" : "muted";
}
function setDbg() {
  document.getElementById("dbg_job").textContent = jobId || "—";
  document.getElementById("dbg_cand").textContent = candidateId || "—";
  document.getElementById("dbg_run").textContent = runId || "—";
}

async function createJob() {
  setText("job_status", "Saving job…");
  const jd_text = document.getElementById("job_text").value || "";
  const title = (jd_text.split("\\n")[0] || "").trim().slice(0, 60) || "Untitled Job"; // backend may require a title
  const payload = {
    title,
    jd_text,
    jd_required_skills: [],   // keep empty (UI no longer asks for them)
    jd_preferred_skills: []   // keep empty
  };
  const r = await fetch("/jobs/", {
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body: JSON.stringify(payload)
  });
  if (!r.ok) { setText("job_status", "Error saving job", false, true); return; }
  const j = await r.json();
  jobId = j.id; setText("job_status", "Job saved ✓", true, false); setDbg();
}

async function createCandidate() {
  setText("cand_status", "Creating candidate…");
  const payload = {
    external_ref: document.getElementById("cand_ref").value || null,
    anonymized: false
  };
  const r = await fetch("/candidates/", {
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body: JSON.stringify(payload)
  });
  if (!r.ok) { setText("cand_status", "Error creating candidate", false, true); return; }
  const j = await r.json();
  candidateId = j.id; setText("cand_status", "Candidate created ✓", true, false); setDbg();
}

async function addCV() {
  if (!candidateId) { setText("cv_status", "Create a candidate first", false, true); return; }
  setText("cv_status", "Attaching CV text…");
  const payload = { type: "cv", text_extracted: document.getElementById("cv_text").value || "", parsed_json: null };
  const r = await fetch(`/candidates/${candidateId}/documents`, {
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body: JSON.stringify(payload)
  });
  if (!r.ok) { setText("cv_status", "Error attaching CV", false, true); return; }
  setText("cv_status", "CV text attached ✓", true, false);
}

async function uploadFile() {
  if (!candidateId) { setText("file_status", "Create a candidate first", false, true); return; }
  const input = document.getElementById("cv_file");
  const file = input.files[0];
  if (!file) { setText("file_status", "Choose a PDF or DOCX", false, true); return; }
  const form = new FormData();
  form.append("file", file);
  setText("file_status", "Uploading…");
  const r = await fetch(`/candidates/${candidateId}/upload`, { method:"POST", body: form });
  if (!r.ok) {
    const msg = await r.text();
    setText("file_status", "Upload failed: " + (msg || r.status), false, true);
    return;
  }
  setText("file_status", "File uploaded ✓", true, false);
}

async function runMatch() {
  if (!jobId) { setText("run_status", "Save the job first", false, true); return; }
  setText("run_status", "Running match…");
  const r = await fetch(`/match/${jobId}/run`, { method:"POST" });
  if (!r.ok) { setText("run_status", "Error running match", false, true); return; }
  const j = await r.json();
  runId = j.id; setText("run_status", "Run created ✓", true, false); setDbg();
}

/* Results: shows candidate name, score, rank, missing skills, and friendly suggestions */
async function getResults() {
  if (!runId) { setText("run_status", "Run the match first", false, true); return; }
  setText("run_status", "Fetching results…");
  const r = await fetch(`/match/${runId}/results?top_n=5`);
  if (!r.ok) { setText("run_status", "Error fetching results", false, true); return; }
  const j = await r.json();
  setText("run_status", "Top-5 loaded ✓", true, false);

  const rows = (j.results || []).map(row => {
    const name = row.candidate_label || row.candidate_id;
    const scorePct = (row.total_score * 100).toFixed(1) + "%";
    const rank = (row.rank != null) ? row.rank : "-";

    const sugg = row.suggestions || {};
    const missing = (sugg.missing_skills || []).map(s => `<span class="chip">${s}</span>`).join(" ");

    const subs = row.subscores || {};
    const req = subs.req_skills != null ? (subs.req_skills * 100).toFixed(0) + "%" : "-";
    const pref = subs.pref_skills != null ? (subs.pref_skills * 100).toFixed(0) + "%" : "-";

    const skills = (sugg.skills_to_surface || []).map(s => `<code>${s}</code>`).join(", ");
    const rewrites = (sugg.bullets_to_rewrite || []).map(o => {
      const esc = s => (s || "").replace(/</g,"&lt;").replace(/>/g,"&gt;");
      return `<div style="margin:.25rem 0"><div class="muted">• ${esc(o.original)}</div><div>↳ ${esc(o.rewrite)}</div></div>`;
    }).join("");

    return `<tr>
      <td>${name}<div class="muted"><code>${row.candidate_id}</code></div></td>
      <td>${scorePct}<div class="muted">req ${req} • pref ${pref}</div></td>
      <td>${rank}</td>
      <td>${missing || "<span class='muted'>(none)</span>"}</td>
      <td>
        <div><span class="muted">Skills to surface:</span> ${skills || "<span class='muted'>(none)</span>"}</div>
        <div style="margin-top:.25rem"><span class="muted">Rewrites:</span> ${rewrites || "<span class='muted'>(none)</span>"}</div>
      </td>
    </tr>`;
  }).join("");

  document.getElementById("results").innerHTML =
    `<table><thead><tr><th>Candidate</th><th>Score</th><th>Rank</th><th>Missing skills</th><th>Suggestions</th></tr></thead><tbody>` +
    (rows || "<tr><td colspan='5'>No results.</td></tr>") + "</tbody></table>";
}
</script>
</body>
</html>
"""

@app.get("/ui", response_class=HTMLResponse)
def ui_page():
    return UI_HTML
