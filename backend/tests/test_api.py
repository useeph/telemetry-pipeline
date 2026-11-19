from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app, get_store
from app.quality import build_report
from app.store import Store

T0 = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


def ev(i, device="truck-1", metric="speed_kph", value=50.0, ts=None):
    return {
        "event_id": f"e{i}",
        "device_id": device,
        "ts": (ts or T0 + timedelta(seconds=i)).isoformat(),
        "metric": metric,
        "value": value,
    }


@pytest.fixture
def store():
    return Store(":memory:")


@pytest.fixture
def client(store):
    app.dependency_overrides[get_store] = lambda: store
    yield TestClient(app)
    app.dependency_overrides.clear()


# ---------- unit: store ----------
def test_store_rejects_duplicate_event_ids(store):
    from app.schemas import TelemetryEvent

    e = TelemetryEvent.model_validate(ev(1))
    assert store.insert_event(e) is True
    assert store.insert_event(e) is False
    assert store.counts() == {"accepted": 1, "rejected": 0, "duplicates": 1}


def test_metrics_bucket_aggregates(store):
    from app.schemas import TelemetryEvent

    for i, v in enumerate([10, 20, 30]):
        store.insert_event(TelemetryEvent.model_validate(ev(i, value=v)))
    rows = store.metrics(60)
    assert len(rows) == 1
    assert rows[0]["count"] == 3 and rows[0]["avg"] == 20 and rows[0]["max"] == 30


def test_metrics_split_across_buckets(store):
    from app.schemas import TelemetryEvent

    store.insert_event(TelemetryEvent.model_validate(ev(1, ts=T0)))
    store.insert_event(TelemetryEvent.model_validate(ev(2, ts=T0 + timedelta(minutes=5))))
    assert len(store.metrics(60)) == 2
    assert len(store.metrics(3600)) == 1


def test_stale_devices_detected(store):
    from app.schemas import TelemetryEvent

    store.insert_event(TelemetryEvent.model_validate(ev(1, device="old", ts=T0)))
    store.insert_event(
        TelemetryEvent.model_validate(ev(2, device="fresh", ts=T0 + timedelta(minutes=30)))
    )
    assert store.stale_devices(T0 + timedelta(minutes=31), 300) == ["old"]


def test_quality_report_passes_on_clean_data(store):
    from app.schemas import TelemetryEvent

    for i in range(10):
        store.insert_event(TelemetryEvent.model_validate(ev(i)))
    report = build_report(store, now=T0 + timedelta(seconds=20))
    assert report.passed is True


def test_quality_report_fails_on_high_reject_rate(store):
    store.dead_letter({"bad": True}, "missing field")
    report = build_report(store, now=T0)
    check = next(c for c in report.checks if c.name == "reject_rate")
    assert check.value == 1.0 and check.passed is False and report.passed is False


# ---------- integration: API ----------
def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_ingest_valid_batch(client):
    r = client.post("/ingest", json=[ev(1), ev(2)])
    assert r.status_code == 200
    assert r.json() == {"accepted": 2, "rejected": 0, "duplicates": 0}


def test_invalid_events_go_to_dead_letter_with_exact_error(client):
    bad = ev(1, metric="altitude")
    r = client.post("/ingest", json=[bad, ev(2)])
    assert r.json() == {"accepted": 1, "rejected": 1, "duplicates": 0}
    dl = client.get("/dead-letter").json()
    assert len(dl) == 1 and dl[0]["error"].startswith("metric:")


def test_naive_timestamp_rejected(client):
    bad = ev(1)
    bad["ts"] = "2026-06-01T12:00:00"
    client.post("/ingest", json=[bad])
    assert "timezone" in client.get("/dead-letter").json()[0]["error"]


def test_metrics_endpoint_filters_by_device(client):
    client.post("/ingest", json=[ev(1, device="a"), ev(2, device="b")])
    rows = client.get("/metrics", params={"device_id": "a"}).json()
    assert {r["device_id"] for r in rows} == {"a"}


def test_quality_endpoint_shape(client):
    client.post("/ingest", json=[ev(1), ev(1)])
    body = client.get("/quality").json()
    assert {c["name"] for c in body["checks"]} == {
        "reject_rate",
        "duplicate_rate",
        "stale_device_rate",
    }
    assert isinstance(body["stale_devices"], list)
