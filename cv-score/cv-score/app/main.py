from fastapi import FastAPI
from .db import Base, engine
from .routers import jobs, candidates, match

Base.metadata.create_all(bind=engine)

app = FastAPI(title="CV Score API", version="0.1.0")

app.include_router(jobs.router)
app.include_router(candidates.router)
app.include_router(match.router)

@app.get("/")
def root():
    return {"service": "cv-score", "status": "ok"}
