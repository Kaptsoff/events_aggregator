from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Event, Place, SyncMetadata, Ticket


class EventRepository:
    def __init__(self, db: Session):
        self.db = db

    def upsert(self, payload: dict) -> Event:
        place_data = payload.get("place") or {}
        place = self.db.get(Place, str(place_data.get("id", "unknown")))
        if place is None:
            place = Place(
                id=str(place_data.get("id", "unknown")),
                name=place_data.get("name", ""),
            )
            self.db.add(place)
            # Ensure the FK target exists before events are flushed in bulk.
            self.db.flush()
        for key in ("name", "city", "address", "seats_pattern"):
            if key in place_data:
                setattr(place, key, place_data[key] or "")
        event = self.db.get(Event, str(payload["id"]))
        if event is None:
            event = Event(
                id=str(payload["id"]),
                name=payload.get("name", ""),
                place_id=place.id,
                event_time=datetime.fromisoformat(payload["event_time"]),
            )
            self.db.add(event)
        event.name = payload.get("name", event.name)
        event.place_id = place.id
        event.event_time = datetime.fromisoformat(payload["event_time"])
        deadline = payload.get("registration_deadline")
        event.registration_deadline = (
            datetime.fromisoformat(deadline) if deadline else None
        )
        event.status = payload.get("status", event.status)
        event.number_of_visitors = int(payload.get("number_of_visitors", 0))
        changed = payload.get("changed_at") or payload.get("created_at")
        event.changed_at = (
            datetime.fromisoformat(changed)
            if changed
            else datetime.now().astimezone()
        )
        return event

    def get(self, event_id: str) -> Optional[tuple[Event, Place]]:
        row = self.db.execute(
            select(Event, Place)
            .join(Place, Event.place_id == Place.id)
            .where(Event.id == event_id)
        ).first()
        return row if row else None


class TicketRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, **kwargs: str) -> Ticket:
        ticket = Ticket(**kwargs)
        self.db.add(ticket)
        self.db.commit()
        return ticket

    def get(self, ticket_id: str) -> Optional[Ticket]:
        return self.db.get(Ticket, ticket_id)

    def delete(self, ticket: Ticket) -> None:
        self.db.delete(ticket)
        self.db.commit()


class SyncRepository:
    def __init__(self, db: Session):
        self.db = db

    def state(self) -> SyncMetadata:
        state = self.db.get(SyncMetadata, 1)
        if state is None:
            state = SyncMetadata(id=1)
            self.db.add(state)
            self.db.commit()
        return state
