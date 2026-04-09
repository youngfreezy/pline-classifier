"""Idempotent seed: load data/mock_tracks.json + data/mock_youtube_cid.json into Postgres."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from sqlalchemy.dialects.postgresql import insert

from app.db import Base, SessionLocal, engine
from app.models import Track, YoutubeCid

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def seed() -> None:
    Base.metadata.create_all(bind=engine)

    tracks = json.loads((DATA_DIR / "mock_tracks.json").read_text())
    cid_map = json.loads((DATA_DIR / "mock_youtube_cid.json").read_text())

    with SessionLocal() as db:
        for t in tracks:
            stmt = insert(Track).values(
                isrc=t["isrc"],
                title=t.get("title"),
                artist=t.get("artist"),
                imprint=t.get("imprint"),
                release_date=_parse_date(t.get("release_date")),
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["isrc"],
                set_={
                    "title": stmt.excluded.title,
                    "artist": stmt.excluded.artist,
                    "imprint": stmt.excluded.imprint,
                    "release_date": stmt.excluded.release_date,
                },
            )
            db.execute(stmt)

        for isrc, c in cid_map.items():
            if c is None:
                continue
            stmt = insert(YoutubeCid).values(
                isrc=isrc,
                asset_id=c.get("asset_id"),
                title=c.get("title"),
                label=c.get("label"),
                owner=c.get("owner"),
                asset_type=c.get("asset_type"),
                artists=c.get("artist"),
                raw=c,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["isrc"],
                set_={
                    "asset_id": stmt.excluded.asset_id,
                    "title": stmt.excluded.title,
                    "label": stmt.excluded.label,
                    "owner": stmt.excluded.owner,
                    "asset_type": stmt.excluded.asset_type,
                    "artists": stmt.excluded.artists,
                    "raw": stmt.excluded.raw,
                },
            )
            db.execute(stmt)

        db.commit()
        print(f"Seeded {len(tracks)} tracks, {sum(1 for v in cid_map.values() if v)} CID rows.")


if __name__ == "__main__":
    seed()
