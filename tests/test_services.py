from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import Event, Place, SyncMetadata, Ticket
from app.provider import EventsProviderClient
from app.services import SeatsService, SyncService, TicketService, list_events


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session


def event_data(event_id="event-1", changed_at="2026-08-31T10:00:00+00:00"):
    return {
        "id": event_id,
        "name": "Python Conference",
        "place": {
            "id": "place-1",
            "name": "Main Hall",
            "city": "Moscow",
            "address": "1 Test Street",
            "seats_pattern": "A1-10",
        },
        "event_time": "2026-09-10T10:00:00+00:00",
        "registration_deadline": "2099-09-09T10:00:00+00:00",
        "status": "published",
        "number_of_visitors": 2,
        "changed_at": changed_at,
    }


def test_sync_upserts_events_and_metadata(db):
    client = Mock(spec=EventsProviderClient)
    client.events.return_value = {"results": [event_data()], "next": None}

    assert SyncService(db, client).run() == 1
    assert db.get(Event, "event-1").name == "Python Conference"
    state = db.get(SyncMetadata, 1)
    assert state.sync_status == "success"
    assert state.last_sync_time is not None


def test_event_list_filters_and_counts_in_sql(db):
    client = Mock(spec=EventsProviderClient)
    client.events.return_value = {
        "results": [event_data("event-1"), event_data("event-2")],
        "next": None,
    }
    SyncService(db, client).run()

    count, results = list_events(db, None, page=1, page_size=1)

    assert count == 2
    assert len(results) == 1


def test_ticket_service_validates_and_persists_ticket(db):
    db.add(Place(id="place-1", name="Main Hall"))
    db.add(
        Event(
            id="event-1",
            name="Python Conference",
            place_id="place-1",
            event_time=datetime.now(timezone.utc) + timedelta(days=2),
            registration_deadline=datetime.now(timezone.utc) + timedelta(days=1),
            status="published",
            number_of_visitors=0,
            changed_at=datetime.now(timezone.utc),
        )
    )
    db.commit()
    client = Mock(spec=EventsProviderClient)
    client.seats.return_value = ["A1"]
    client.register.return_value = "ticket-1"

    ticket = TicketService(db, client).create(
        "event-1", "Ivan", "Ivanov", "ivan@example.com", "A1"
    )

    assert ticket.ticket_id == "ticket-1"
    client.register.assert_called_once()


def test_seats_service_caches_provider_result(db):
    db.add(Place(id="place-1", name="Main Hall"))
    db.add(
        Event(
            id="event-1",
            name="Python Conference",
            place_id="place-1",
            event_time=datetime.now(timezone.utc) + timedelta(days=2),
            registration_deadline=None,
            status="published",
            number_of_visitors=0,
            changed_at=datetime.now(timezone.utc),
        )
    )
    db.commit()
    client = Mock(spec=EventsProviderClient)
    client.seats.return_value = ["A1"]

    service = SeatsService(db, client)
    assert service.get("event-1") == ["A1"]
    assert service.get("event-1") == ["A1"]
    client.seats.assert_called_once_with("event-1")


def test_ticket_service_cancels_ticket(db):
    db.add(Place(id="place-1", name="Main Hall"))
    db.add(
        Event(
            id="event-1",
            name="Python Conference",
            place_id="place-1",
            event_time=datetime.now(timezone.utc) + timedelta(days=2),
            registration_deadline=None,
            status="published",
            number_of_visitors=0,
            changed_at=datetime.now(timezone.utc),
        )
    )
    db.commit()
    db.add(
        Ticket(
            ticket_id="ticket-1",
            event_id="event-1",
            first_name="Ivan",
            last_name="Ivanov",
            email="ivan@example.com",
            seat="A1",
        )
    )
    db.commit()
    client = Mock(spec=EventsProviderClient)

    assert TicketService(db, client).cancel("ticket-1") is True
    client.unregister.assert_called_once_with("event-1", "ticket-1")
