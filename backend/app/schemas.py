"""Typed schemas for incoming telemetry and API responses."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

MetricName = Literal["temperature_c", "battery_v", "speed_kph", "rpm"]


class TelemetryEvent(BaseModel):
    """One reading reported by a device."""

    event_id: str = Field(min_length=1, max_length=64)
    device_id: str = Field(min_length=1, max_length=64)
    ts: datetime
    metric: MetricName
    value: float

    @field_validator("ts")
    @classmethod
    def ts_must_have_timezone(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("timestamp must include a timezone offset")
        return v


class IngestResult(BaseModel):
    accepted: int
    rejected: int
    duplicates: int


class MetricBucket(BaseModel):
    bucket_start: datetime
    device_id: str
    metric: str
    count: int
    avg: float
    min: float
    max: float


class QualityCheck(BaseModel):
    name: str
    value: float
    threshold: float
    passed: bool


class QualityReport(BaseModel):
    passed: bool
    checks: list[QualityCheck]
    stale_devices: list[str]
