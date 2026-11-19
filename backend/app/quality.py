"""Data-quality checks with pass/fail thresholds."""

import os
from datetime import UTC, datetime

from .schemas import QualityCheck, QualityReport
from .store import Store

MAX_REJECT_RATE = float(os.getenv("MAX_REJECT_RATE", "0.05"))
MAX_DUPLICATE_RATE = float(os.getenv("MAX_DUPLICATE_RATE", "0.02"))
MAX_STALE_RATE = float(os.getenv("MAX_STALE_RATE", "0.10"))
STALE_AFTER_SECONDS = int(os.getenv("STALE_AFTER_SECONDS", "300"))


def _rate(part: int, whole: int) -> float:
    return round(part / whole, 4) if whole else 0.0


def build_report(store: Store, now: datetime | None = None) -> QualityReport:
    now = now or datetime.now(UTC)
    c = store.counts()
    received = c["accepted"] + c["rejected"] + c["duplicates"]
    stale = store.stale_devices(now, STALE_AFTER_SECONDS)
    devices = store.device_count()

    checks = [
        QualityCheck(
            name="reject_rate",
            value=_rate(c["rejected"], received),
            threshold=MAX_REJECT_RATE,
            passed=_rate(c["rejected"], received) <= MAX_REJECT_RATE,
        ),
        QualityCheck(
            name="duplicate_rate",
            value=_rate(c["duplicates"], received),
            threshold=MAX_DUPLICATE_RATE,
            passed=_rate(c["duplicates"], received) <= MAX_DUPLICATE_RATE,
        ),
        QualityCheck(
            name="stale_device_rate",
            value=_rate(len(stale), devices),
            threshold=MAX_STALE_RATE,
            passed=_rate(len(stale), devices) <= MAX_STALE_RATE,
        ),
    ]
    return QualityReport(
        passed=all(ch.passed for ch in checks), checks=checks, stale_devices=stale
    )
