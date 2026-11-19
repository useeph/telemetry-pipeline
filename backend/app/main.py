"""FastAPI service: validated telemetry ingestion, aggregates, and data quality."""

import os
from typing import Any

from fastapi import Depends, FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError

from .quality import build_report
from .schemas import IngestResult, MetricBucket, QualityReport, TelemetryEvent
from .store import Store

_store = Store(os.getenv("DB_PATH", ":memory:"))


def get_store() -> Store:
    return _store


app = FastAPI(title="Telemetry Pipeline", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv(
        "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


def _format_error(err: ValidationError) -> str:
    parts = []
    for e in err.errors():
        loc = ".".join(str(x) for x in e["loc"]) or "body"
        parts.append(f"{loc}: {e['msg']}")
    return "; ".join(parts)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/ingest", response_model=IngestResult)
def ingest(
    payload: list[dict[str, Any]], store: Store = Depends(get_store)
) -> IngestResult:
    """Accept a batch of events. Invalid ones go to the dead-letter table with the
    exact validation error instead of failing the whole batch."""
    accepted = rejected = duplicates = 0
    for raw in payload:
        try:
            event = TelemetryEvent.model_validate(raw)
        except ValidationError as err:
            store.dead_letter(raw, _format_error(err))
            rejected += 1
            continue
        if store.insert_event(event):
            accepted += 1
        else:
            duplicates += 1
    return IngestResult(accepted=accepted, rejected=rejected, duplicates=duplicates)


@app.get("/metrics", response_model=list[MetricBucket])
def metrics(
    bucket_seconds: int = Query(60, ge=1, le=86400),
    device_id: str | None = None,
    store: Store = Depends(get_store),
):
    return store.metrics(bucket_seconds, device_id)


@app.get("/dead-letter")
def dead_letter(limit: int = Query(50, ge=1, le=500), store: Store = Depends(get_store)):
    return store.dead_letters(limit)


@app.get("/quality", response_model=QualityReport)
def quality(store: Store = Depends(get_store)) -> QualityReport:
    return build_report(store)
