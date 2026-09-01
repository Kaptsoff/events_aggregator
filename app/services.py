import logging
import threading
import time
from datetime import date, datetime, timezone
from datetime import time as datetime_time
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .enums import EventStatus, SyncStatus
from .models import Event, Place
from .provider import EventsPaginator, EventsProviderClient
from .repositories import EventRepository, SyncRepository, TicketRepository

logger = logging.getLogger(__name__)
_sync_lock = threading.Lock()
_seats_cache: dict[str, tuple[float, list[str]]] = {}


class SyncAlreadyRunningError(RuntimeError):
    pass


class EventNotFound(LookupError):
    pass


class TicketNotFound(LookupError):
    pass


class EventNotPublished(ValueError):
    pass


class RegistrationDeadlinePassed(ValueError):
    pass


class SeatNotAvailable(ValueError):
    pass


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class SyncService:
    def __init__(self, db: Session, client: EventsProviderClient):
        self.db = db
        self.client = client

    def run(self) -> int:
        if not _sync_lock.acquire(blocking=False):
            raise SyncAlreadyRunningError("Synchronization is already running")
        try:
            return self._run_locked()
        finally:
            _sync_lock.release()

    def _run_locked(self) -> int:
        sync = SyncRepository(self.db).state()
        changed_at = sync.last_changed_at.date().isoformat()
        sync.sync_status = SyncStatus.RUNNING.value
        self.db.commit()
        count = 0
        newest = _utc(sync.last_changed_at)
        try:
            for payload in EventsPaginator(self.client, changed_at):
                EventRepository(self.db).upsert(payload)
                changed = payload.get("changed_at") or payload.get("created_at")
                if changed:
                    newest = max(newest, _utc(datetime.fromisoformat(changed)))
                count += 1
            sync.last_changed_at = newest
            sync.last_sync_time = datetime.now(timezone.utc)
            sync.sync_status = SyncStatus.SUCCESS.value
            self.db.commit()
            logger.info("Synchronized %s events", count)
            return count
        except Exception:
            self.db.rollback()
            sync = SyncRepository(self.db).state()
            sync.sync_status = SyncStatus.ERROR.value
            sync.last_sync_time = datetime.now(timezone.utc)
            self.db.commit()
            logger.exception("Event synchronization failed")
            raise


def event_payload(db: Session, event_id: str) -> Optional[dict]:
    row = EventRepository(db).get(event_id)
    if not row:
        return None
    event, place = row
    return {
        "id": event.id,
        "name": event.name,
        "place": {
            "id": place.id,
            "name": place.name,
            "city": place.city,
            "address": place.address,
            "seats_pattern": place.seats_pattern,
        },
        "event_time": event.event_time.isoformat(),
        "registration_deadline": (
            event.registration_deadline.isoformat()
            if event.registration_deadline
            else None
        ),
        "status": event.status,
        "number_of_visitors": event.number_of_visitors,
    }


def list_events(
    db: Session, date_from: Optional[date], page: int, page_size: int
) -> tuple[int, list[dict]]:
    query = select(Event, Place).join(Place, Event.place_id == Place.id)
    if date_from:
        start = datetime.combine(date_from, datetime_time.min, tzinfo=timezone.utc)
        query = query.where(Event.event_time >= start)
    rows = db.execute(
        query.order_by(Event.event_time)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    count_query = select(func.count()).select_from(Event)
    if date_from:
        count_query = count_query.where(Event.event_time >= start)
    count = db.scalar(count_query) or 0
    return count, [event_payload_from_row(event, place) for event, place in rows]


def event_payload_from_row(event: Event, place: Place) -> dict:
    return {
        "id": event.id,
        "name": event.name,
        "place": {
            "id": place.id,
            "name": place.name,
            "city": place.city,
            "address": place.address,
        },
        "event_time": event.event_time.isoformat(),
        "registration_deadline": (
            event.registration_deadline.isoformat()
            if event.registration_deadline
            else None
        ),
        "status": event.status,
        "number_of_visitors": event.number_of_visitors,
    }


class TicketService:
    def __init__(self, db: Session, client: EventsProviderClient):
        self.db, self.client = db, client

    def create(
        self,
        event_id: str,
        first_name: str,
        last_name: str,
        email: str,
        seat: str,
    ):
        row = EventRepository(self.db).get(event_id)
        if not row:
            raise EventNotFound("Event not found")
        event, _ = row
        if event.status != EventStatus.PUBLISHED:
            raise EventNotPublished("Event is not published")
        deadline = event.registration_deadline
        if deadline and datetime.now(timezone.utc) > _utc(deadline):
            raise RegistrationDeadlinePassed("Registration deadline has passed")
        if seat not in self.client.seats(event_id):
            raise SeatNotAvailable("Seat is not available")
        ticket_id = self.client.register(event_id, first_name, last_name, email, seat)
        return TicketRepository(self.db).create(
            ticket_id=ticket_id,
            event_id=event_id,
            first_name=first_name,
            last_name=last_name,
            email=email,
            seat=seat,
        )

    def cancel(self, ticket_id: str) -> bool:
        repository = TicketRepository(self.db)
        ticket = repository.get(ticket_id)
        if ticket is None:
            raise TicketNotFound("Ticket not found")
        self.client.unregister(ticket.event_id, ticket.ticket_id)
        repository.delete(ticket)
        return True


class SeatsService:
    def __init__(self, db: Session, client: EventsProviderClient):
        self.db, self.client = db, client

    def get(self, event_id: str) -> list[str]:
        if EventRepository(self.db).get(event_id) is None:
            raise EventNotFound("Event not found")
        now = time.monotonic()
        cached = _seats_cache.get(event_id)
        if cached and now - cached[0] < 30:
            return cached[1]
        values = self.client.seats(event_id)
        _seats_cache[event_id] = (now, values)
        return values
