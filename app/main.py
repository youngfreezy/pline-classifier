from fastapi import FastAPI

from app.db import Base, engine
from app.routers import classify, tracks

app = FastAPI(title="P-Line Track API", version="0.1.0")


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(tracks.router)
app.include_router(classify.router)
