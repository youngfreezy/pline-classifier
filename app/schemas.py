from datetime import date

from pydantic import BaseModel, ConfigDict


class TrackInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    title: str | None
    artist: str | None
    imprint: str | None
    release_date: date | None


class CidInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    asset_id: str | None
    label: str | None
    owner: str | None
    asset_type: str | None
    artists: list[str] | None


class TrackResponse(BaseModel):
    isrc: str
    track: TrackInfo
    cid: CidInfo | None


class TrackListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[TrackResponse]
