# CV Score API

This is a FastAPI backend to upload Job Descriptions (JDs) and CVs, score/rank candidates, and generate suggestions to reach the Top-5 threshold.

## Local quick start (optional)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/cvscore
uvicorn app.main:app --reload
```

Open http://localhost:8000/docs
