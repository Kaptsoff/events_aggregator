from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class Place(Base):
    __tablename__ = "places"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    city: Mapped[str] = mapped_column(String(255), default="")
    address: Mapped[str] = mapped_column(Text, default="")
    seats_pattern: Mapped[str] = mapped_column(Text, default="")


class Event(Base):
    __tablename__ = "events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    place_id: Mapped[str] = mapped_column(ForeignKey("places.id"), index=True)
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    registration_deadline: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    status: Mapped[str] = mapped_column(String(32), default="new")
    number_of_visitors: Mapped[int] = mapped_column(Integer, default=0)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Ticket(Base):
    __tablename__ = "tickets"

    ticket_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_id: Mapped[str] = mapped_column(
        ForeignKey("events.id"), index=True
    )
    first_name: Mapped[str] = mapped_column(String(255))
    last_name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(320))
    seat: Mapped[str] = mapped_column(String(64))


class SyncMetadata(Base):
    __tablename__ = "sync_metadata"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    last_sync_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    last_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime(2000, 1, 1, tzinfo=timezone.utc),
    )
    sync_status: Mapped[str] = mapped_column(String(32), default="never")
