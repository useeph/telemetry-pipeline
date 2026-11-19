"""Send simulated device telemetry to the API, including some bad and duplicate events.

Usage: python scripts/simulate.py --url http://localhost:8000 --devices 5 --batches 20
"""

import argparse
import json
import random
import time
import urllib.request
import uuid
from datetime import UTC, datetime

METRICS = {
    "temperature_c": (20, 90),
    "battery_v": (11.5, 14.5),
    "speed_kph": (0, 110),
    "rpm": (700, 3200),
}


def make_event(device_id: str) -> dict:
    metric = random.choice(list(METRICS))
    lo, hi = METRICS[metric]
    return {
        "event_id": uuid.uuid4().hex,
        "device_id": device_id,
        "ts": datetime.now(UTC).isoformat(),
        "metric": metric,
        "value": round(random.uniform(lo, hi), 2),
    }


def corrupt(event: dict) -> dict:
    bad = dict(event)
    choice = random.choice(["metric", "value", "ts", "missing"])
    if choice == "metric":
        bad["metric"] = "altitude"
    elif choice == "value":
        bad["value"] = "not-a-number"
    elif choice == "ts":
        bad["ts"] = bad["ts"][:19]  # strip timezone
    else:
        bad.pop("device_id")
    return bad


def post(url: str, batch: list[dict]) -> dict:
    req = urllib.request.Request(
        f"{url}/ingest",
        data=json.dumps(batch).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--url", default="http://localhost:8000")
    p.add_argument("--devices", type=int, default=5)
    p.add_argument("--batches", type=int, default=20)
    p.add_argument("--bad-rate", type=float, default=0.03)
    p.add_argument("--interval", type=float, default=1.0)
    args = p.parse_args()

    devices = [f"truck-{i + 1}" for i in range(args.devices)]
    for n in range(args.batches):
        batch = [make_event(d) for d in devices for _ in range(3)]
        batch = [corrupt(e) if random.random() < args.bad_rate else e for e in batch]
        if random.random() < 0.2:
            batch.append(dict(batch[0]))  # occasional duplicate retry
        print(f"batch {n + 1}: {post(args.url, batch)}")
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
