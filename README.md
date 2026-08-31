# Events Aggregator

FastAPI service that caches Events Provider events in PostgreSQL and exposes a page-based REST API.

Run locally:

```bash
python -m pip install -e ".[test]"
uvicorn app.main:app --reload
```

Configure `DATABASE_URL`, `EVENTS_PROVIDER_URL` and `EVENTS_PROVIDER_API_KEY` with environment variables.
"# events_aggregator" 
