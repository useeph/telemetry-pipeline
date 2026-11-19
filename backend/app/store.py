"""DuckDB storage: accepted events, a dead-letter table, and aggregate queries."""

import json
import threading
from datetime import UTC, datetime

import duckdb

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    event_id   VARCHAR PRIMARY KEY,
    device_id  VARCHAR NOT NULL,
    ts         TIMESTAMPTZ NOT NULL,
    metric     VARCHAR NOT NULL,
    value      DOUBLE NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS dead_letter (
    received_at TIMESTAMPTZ NOT NULL,
    payload     VARCHAR NOT NULL,
    error       VARCHAR NOT NULL
);
CREATE TABLE IF NOT EXISTS duplicate_log (
    event_id    VARCHAR NOT NULL,
    received_at TIMESTAMPTZ NOT NULL
);
"""


class Store:
    def __init__(self, path: str = ":memory:"):
        self.con = duckdb.connect(path)
        self.con.execute("SET TimeZone = 'UTC'")
        self.con.execute(SCHEMA)
        self.lock = threading.Lock()

    # ---------- writes ----------
    def insert_event(self, e) -> bool:
        """Insert an accepted event. Returns False if event_id was already seen."""
        now = datetime.now(UTC)
        with self.lock:
            exists = self.con.execute(
                "SELECT 1 FROM events WHERE event_id = ?", [e.event_id]
            ).fetchone()
            if exists:
                self.con.execute(
                    "INSERT INTO duplicate_log VALUES (?, ?)", [e.event_id, now]
                )
                return False
            self.con.execute(
                "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?)",
                [e.event_id, e.device_id, e.ts, e.metric, e.value, now],
            )
            return True

    def dead_letter(self, payload, error: str) -> None:
        with self.lock:
            self.con.execute(
                "INSERT INTO dead_letter VALUES (?, ?, ?)",
                [datetime.now(UTC), json.dumps(payload, default=str), error],
            )

    # ---------- reads ----------
    def _query(self, sql: str, params: list | None = None) -> list[tuple]:
        """DuckDB connections are not safe for concurrent use; serialize access."""
        with self.lock:
            return self.con.execute(sql, params or []).fetchall()

    def dead_letters(self, limit: int = 50) -> list[dict]:
        rows = self._query(
            "SELECT received_at, payload, error FROM dead_letter "
            "ORDER BY received_at DESC LIMIT ?",
            [limit],
        )
        return [{"received_at": r[0], "payload": r[1], "error": r[2]} for r in rows]

    def metrics(self, bucket_seconds: int, device_id: str | None = None) -> list[dict]:
        # Portable time bucketing: floor(epoch / size) * size works in most SQL engines.
        sql = """
            SELECT to_timestamp(floor(epoch(ts) / ?) * ?) AS bucket_start,
                   device_id, metric, count(*) AS n,
                   avg(value), min(value), max(value)
            FROM events
            WHERE (? IS NULL OR device_id = ?)
            GROUP BY ALL
            ORDER BY bucket_start, device_id, metric
        """
        rows = self._query(sql, [bucket_seconds, bucket_seconds, device_id, device_id])
        return [
            {
                "bucket_start": r[0],
                "device_id": r[1],
                "metric": r[2],
                "count": r[3],
                "avg": round(r[4], 3),
                "min": r[5],
                "max": r[6],
            }
            for r in rows
        ]

    def counts(self) -> dict:
        accepted = self._query("SELECT count(*) FROM events")[0][0]
        rejected = self._query("SELECT count(*) FROM dead_letter")[0][0]
        dupes = self._query("SELECT count(*) FROM duplicate_log")[0][0]
        return {"accepted": accepted, "rejected": rejected, "duplicates": dupes}

    def stale_devices(self, now: datetime, stale_after_seconds: int) -> list[str]:
        rows = self._query(
            """
            SELECT device_id FROM events
            GROUP BY device_id
            HAVING epoch(?::TIMESTAMPTZ) - epoch(max(ts)) > ?
            ORDER BY device_id
            """,
            [now, stale_after_seconds],
        )
        return [r[0] for r in rows]

    def device_count(self) -> int:
        return self._query("SELECT count(DISTINCT device_id) FROM events")[0][0]
