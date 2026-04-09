from datetime import date

from sqlalchemy import Date, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Track(Base):
    __tablename__ = "tracks"

    isrc: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str | None] = mapped_column(String)
    artist: Mapped[str | None] = mapped_column(String)
    imprint: Mapped[str | None] = mapped_column(String)
    release_date: Mapped[date | None] = mapped_column(Date)

    cid: Mapped["YoutubeCid | None"] = relationship(
        back_populates="track", uselist=False, lazy="joined"
    )


class YoutubeCid(Base):
    __tablename__ = "youtube_cid"

    isrc: Mapped[str] = mapped_column(
        String, ForeignKey("tracks.isrc"), primary_key=True
    )
    asset_id: Mapped[str | None] = mapped_column(String)
    title: Mapped[str | None] = mapped_column(String)
    label: Mapped[str | None] = mapped_column(String)
    owner: Mapped[str | None] = mapped_column(String)
    asset_type: Mapped[str | None] = mapped_column(String)
    artists: Mapped[list | None] = mapped_column(JSONB)
    raw: Mapped[dict | None] = mapped_column(JSONB)

    track: Mapped[Track] = relationship(back_populates="cid")
