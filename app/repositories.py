from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import Track


def get_track(db: Session, isrc: str) -> Track | None:
    return db.get(Track, isrc)


def list_tracks(
    db: Session, limit: int = 50, offset: int = 0, q: str | None = None
) -> tuple[int, list[Track]]:
    stmt = select(Track)
    count_stmt = select(func.count()).select_from(Track)

    if q:
        like = f"%{q}%"
        cond = or_(
            Track.title.ilike(like),
            Track.artist.ilike(like),
            Track.imprint.ilike(like),
            Track.isrc.ilike(like),
        )
        stmt = stmt.where(cond)
        count_stmt = count_stmt.where(cond)

    total = db.execute(count_stmt).scalar_one()
    rows = db.execute(stmt.order_by(Track.isrc).limit(limit).offset(offset)).scalars().unique().all()
    return total, list(rows)
