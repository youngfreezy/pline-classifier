from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import repositories
from app.db import get_db
from app.models import Track
from app.schemas import CidInfo, TrackInfo, TrackListResponse, TrackResponse

router = APIRouter(prefix="/tracks", tags=["tracks"])


def _to_response(track: Track) -> TrackResponse:
    return TrackResponse(
        isrc=track.isrc,
        track=TrackInfo.model_validate(track),
        cid=CidInfo.model_validate(track.cid) if track.cid else None,
    )


@router.get("", response_model=TrackListResponse)
def list_tracks(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    q: str | None = Query(None, description="Search title/artist/imprint/isrc"),
    db: Session = Depends(get_db),
):
    total, rows = repositories.list_tracks(db, limit=limit, offset=offset, q=q)
    return TrackListResponse(
        total=total,
        limit=limit,
        offset=offset,
        items=[_to_response(t) for t in rows],
    )


@router.get("/{isrc}", response_model=TrackResponse)
def get_track(isrc: str, db: Session = Depends(get_db)):
    track = repositories.get_track(db, isrc)
    if not track:
        raise HTTPException(status_code=404, detail=f"Track {isrc} not found")
    return _to_response(track)
