import asyncio
from datetime import datetime, timezone

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import Event, Place


def test_health_and_paginated_events_preserve_filter():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(Place(id="place-1", name="Main Hall"))
        for index in range(2):
            db.add(
                Event(
                    id=f"event-{index}",
                    name=f"Event {index}",
                    place_id="place-1",
                    event_time=datetime(2026, 9, 10 + index, tzinfo=timezone.utc),
                    registration_deadline=None,
                    status="published",
                    number_of_visitors=0,
                    changed_at=datetime.now(timezone.utc),
                )
            )
        db.commit()

    def override_db():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    try:
        async def run() -> None:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
            ) as client:
                assert (await client.get("/api/health")).json() == {"status": "ok"}
                response = await client.get(
                    "/api/events",
                    params={"date_from": "2026-09-10", "page_size": 1},
                )
                assert response.status_code == 200
                payload = response.json()
                assert payload["count"] == 2
                assert "date_from=2026-09-10" in payload["next"]

        asyncio.run(run())
    finally:
        app.dependency_overrides.clear()
