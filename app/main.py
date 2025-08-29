from fastapi import FastAPI, Response
from fastapi.responses import HTMLResponse
from .db import Base, engine
from .routers import jobs, candidates, match

# Create tables at startup (simple demo behavior)
Base.metadata.create_all(bind=engine)

app = FastAPI(title="CV Score API", version="0.2.0")

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

# ---- Minimal web UI at /ui (inline HTML, includes PDF/DOCX upload) ----
UI_HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>CV Score – Mini UI (with Uploads)</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <style>
    :root { font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; }
    body { max-width: 960px; margin: 24px auto; padding: 0 12px; }
    h1 { margin: 0 0 8px; }
    .card { border: 1px solid #ddd; border-radius: 12px; padding: 16px; margin: 12px 0; }
    label { display:block; font-weight:600; margin: 10px 0 6px; }
    input[type=text], textarea { width: 100%; padding: 10px; border: 1px solid #ccc; border-radius: 8px; }
    textarea { min-height: 110px; }
    .row { display: grid; grid-template-columns:1fr 1fr; gap: 12px; }
    button { padding: 10px 14px; border: 0; border-radius: 10px; background: #111827; color: #fff; cursor: pointer; }
    button.secondary { background:#4b5563; }
    .pill { display:inline-block; background:#eef2ff; color:#3730a3; padding:4px 8px; border-radius:999px; font-size:12px; margin-left:8px;}
    .muted { color:#6b7280; font-size: 12px; }
    pre { white-space: pre-wrap; word-break: break-word; }
    table { width: 100%; border-collapse: collapse; margin-top: 8px; }
    th, td { padding: 8px; border-bottom: 1px solid #eee; text-align: left; vertical-align: top; }
    .ok { color: #065f46; }
    .err { color: #7f1d1d; }
    input[type=file]{margin-top:6px}
  </style>
</head>
<body>
  <h1>CV Score <span class="pill">mini UI + uploads</span></h1>
  <p class="muted">Create a Job, add Candidates & CVs (paste text or upload PDF/DOCX), then run matching and see the Top-5 with suggestions.</p>

  <div class="card">
    <h2>1) Create Job</h2>
    <div class="row">
      <div>
        <label>Job Title</label>
        <input id="job_title" type="text" placeholder="e.g., data engineer" />
      </div>
      <div>
        <label>Required skills (comma-separated)</label>
        <input id="job_req" type="text" placeholder="etl, airflow, spark" />
      </div>
    </div>
    <label>Preferred skills (comma-separated)</label>
    <input id="job_pref" type="text" placeholder="databricks, delta lake" />
    <label>Job description text</label>
    <textarea id="job_text" placeholder="We need ETL, Airflow, Spark, Databricks, Delta Lake"></textarea>
    <div style="margin-top:12px; display:flex; gap:8px;">
      <button onclick="createJob()">Create Job</button>
      <span id="job_status" class="muted"></span>
    </div>
  </div>

  <div class="card">
    <h2>2) Create Candidate & Add CV</h2>
    <div class="row">
      <div>
        <label>External Ref (optional)</label>
        <input id="cand_ref" type="text" placeholder="cand-001" />
      </div>
      <div>
        <label>Anon?</label>
        <input id="cand_anon" type="checkbox" />
      </div>
    </div>
    <div style="margin-top:8px;">
      <button onclick="createCandidate()">Create Candidate</button>
      <span id="cand_status" class="muted"></span>
    </div>

    <label style="margin-top:12px;">CV Text (optional)</label>
    <textarea id="cv_text" placeholder="- Built ETL jobs in Airflow...
- Migrated pipelines to Spark on Databricks..."></textarea>
    <div style="margin-top:8px;">
      <button class="secondary" onclick="addCV()">Attach CV</button>
      <span id="cv_status" class="muted"></span>
    </div>

    <div style="margin-top:16px; padding-top:12px; border-top:1px dashed #ddd;">
      <label>Upload PDF/DOCX</label>
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
    <h2>Debug values</h2>
    <div class="muted">Job ID: <span id="dbg_job"></span> • Candidate ID: <span id="dbg_cand"></span> • Run ID: <span id="dbg_run"></span></div>
  </div>

<script>
let jobId = null;
let candidateId = null;
let runId = null;

function commaToArray(s) {
  return (s || "").split(",").map(x => x.trim()).filter(Boolean);
}
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
  setText("job_status", "Creating job…");
  const payload = {
    title: document.getElementById("job_title").value || "data engineer",
    jd_text: document.getElementById("job_text").value || "We need ETL, Airflow, Spark, Databricks, Delta Lake",
    jd_required_skills: commaToArray(document.getElementById("job_req").value || "etl, airflow, spark"),
    jd_preferred_skills: commaToArray(document.getElementById("job_pref").value || "databricks, delta lake")
  };
  const r = await fetch("/jobs/", {
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body: JSON.stringify(payload)
  });
  if (!r.ok) { setText("job_status", "Error creating job", false, true); return; }
  const j = await r.json();
  jobId = j.id; setText("job_status", "Job created ✓", true, false); setDbg();
}

async function createCandidate() {
  setText("cand_status", "Creating candidate…");
  const payload = {
    external_ref: document.getElementById("cand_ref").value || null,
    anonymized: document.getElementById("cand_anon").checked || false
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
  setText("cv_status", "Uploading CV…");
  const payload = { type: "cv", text_extracted: document.getElementById("cv_text").value || "", parsed_json: null };
  const r = await fetch(`/candidates/${candidateId}/documents`, {
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body: JSON.stringify(payload)
  });
  if (!r.ok) { setText("cv_status", "Error attaching CV", false, true); return; }
  setText("cv_status", "CV attached ✓", true, false);
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
  if (!jobId) { setText("run_status", "Create a job first", false, true); return; }
  setText("run_status", "Running match…");
  const r = await fetch(`/match/${jobId}/run`, { method:"POST" });
  if (!r.ok) { setText("run_status", "Error running match", false, true); return; }
  const j = await r.json();
  runId = j.id; setText("run_status", "Run created ✓", true, false); setDbg();
}
