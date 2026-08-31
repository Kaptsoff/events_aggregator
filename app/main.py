import asyncio
import logging
import time
from contextlib import asynccontextmanager
from datetime import date
from typing import Annotated, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from .config import get_settings
from .db import SessionLocal, get_db, init_db
from .provider import EventsProviderClient, EventsProviderError
from .repositories import TicketRepository
from .services import (
    SyncAlreadyRunningError,
    SyncService,
    TicketService,
    event_payload,
    list_events,
)

logging.basicConfig(level=logging.INFO)
settings = get_settings()
seats_cache: dict[str, tuple[float, list[str]]] = {}


def client() -> EventsProviderClient:
    return EventsProviderClient(
        settings.events_provider_url,
        settings.events_provider_api_key,
        settings.request_timeout_seconds,
    )


async def worker() -> None:
    while True:
        # Manual trigger should be available immediately after deployment.
        await asyncio.sleep(settings.sync_interval_seconds)
        if settings.events_provider_api_key:
            try:
                with SessionLocal() as db:
                    await asyncio.to_thread(SyncService(db, client()).run)
            except Exception:
                logging.exception("Scheduled synchronization failed")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    task = asyncio.create_task(worker())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="Events Aggregator", lifespan=lifespan)
DB = Annotated[Session, Depends(get_db)]


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    if request.url.path == "/api/tickets":
        return JSONResponse(
            status_code=400, content={"detail": jsonable_encoder(exc.errors())}
        )
    return JSONResponse(
        status_code=422, content={"detail": jsonable_encoder(exc.errors())}
    )


class TicketRequest(BaseModel):
    event_id: str
    first_name: str = Field(min_length=1)
    last_name: str = Field(min_length=1)
    email: EmailStr
    seat: str = Field(min_length=1)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/sync/trigger")
def trigger_sync(db: DB):
    try:
        return {"synchronized": SyncService(db, client()).run()}
    except EventsProviderError as exc:
        raise HTTPException(502, str(exc)) from exc
    except SyncAlreadyRunningError:
        return {"synchronized": 0, "status": "running"}


@app.get("/api/events")
def events(
    request: Request,
    db: DB,
    date_from: Optional[date] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    count, results = list_events(db, date_from, page, page_size)
    next_url = None
    previous_url = None
    if page * page_size < count:
        next_url = str(
            request.url.include_query_params(page=page + 1, page_size=page_size)
        )
    if page > 1:
        previous_url = str(
            request.url.include_query_params(page=page - 1, page_size=page_size)
        )
    return {
        "count": count,
        "next": next_url,
        "previous": previous_url,
        "results": results,
    }


@app.get("/api/events/{event_id}")
def event(event_id: str, db: DB):
    payload = event_payload(db, event_id)
    if payload is None:
        raise HTTPException(404, "Event not found")
    return payload


@app.get("/api/events/{event_id}/seats")
def seats(event_id: str, db: DB):
    if event_payload(db, event_id) is None:
        raise HTTPException(404, "Event not found")
    now = time.monotonic()
    cached = seats_cache.get(event_id)
    if cached and now - cached[0] < 30:
        return {"event_id": event_id, "available_seats": cached[1]}
    try:
        values = client().seats(event_id)
    except EventsProviderError as exc:
        raise HTTPException(502, str(exc)) from exc
    seats_cache[event_id] = (now, values)
    return {"event_id": event_id, "available_seats": values}


@app.post("/api/tickets", status_code=status.HTTP_201_CREATED)
def create_ticket(request: TicketRequest, db: DB):
    try:
        ticket = TicketService(db, client()).create(**request.model_dump())
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except EventsProviderError as exc:
        raise HTTPException(502, str(exc)) from exc
    return {"ticket_id": ticket.ticket_id}


@app.delete("/api/tickets/{ticket_id}")
def cancel_ticket(ticket_id: str, db: DB):
    repo = TicketRepository(db)
    ticket = repo.get(ticket_id)
    if ticket is None:
        raise HTTPException(404, "Ticket not found")
    try:
        client().unregister(ticket.event_id, ticket.ticket_id)
    except EventsProviderError as exc:
        raise HTTPException(502, str(exc)) from exc
    repo.delete(ticket)
    return {"success": True}
