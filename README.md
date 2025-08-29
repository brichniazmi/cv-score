# CV Score API (Render-ready)

## Render settings
**Build Command**
```
pip install -r requirements.txt
```
**Start Command**
```
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```
**Env var**
```
DATABASE_URL = <Render Postgres Internal Database URL>
```

## Test
Open `/` for health and `/docs` for API UI.
