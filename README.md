# CV Score API (Render-ready, Python 3.11)

**Render settings**  
Build: `pip install -r requirements.txt`  
Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`  
Env: `DATABASE_URL=<Render Postgres Internal Database URL>`

This package pins Python via `.python-version` to `3.11.9` to avoid psycopg2/CPython 3.13 ABI issues.
