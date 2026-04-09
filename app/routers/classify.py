from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import repositories
from app.classifier.service import Classification, ClassifierService
from app.db import get_db

router = APIRouter(tags=["classify"])


@lru_cache(maxsize=1)
def get_classifier() -> ClassifierService:
    return ClassifierService()


class BatchRequest(BaseModel):
    isrcs: list[str]


class BatchResponse(BaseModel):
    results: list[Classification]


@router.post("/tracks/{isrc}/classify", response_model=Classification)
def classify_track(
    isrc: str,
    db: Session = Depends(get_db),
    svc: ClassifierService = Depends(get_classifier),
):
    track = repositories.get_track(db, isrc)
    if not track:
        raise HTTPException(status_code=404, detail=f"Track {isrc} not found")
    return svc.classify(track)


@router.post("/classify/batch", response_model=BatchResponse)
def classify_batch(
    body: BatchRequest,
    db: Session = Depends(get_db),
    svc: ClassifierService = Depends(get_classifier),
):
    results: list[Classification] = []
    for isrc in body.isrcs:
        track = repositories.get_track(db, isrc)
        if not track:
            raise HTTPException(status_code=404, detail=f"Track {isrc} not found")
        results.append(svc.classify(track))
    return BatchResponse(results=results)
