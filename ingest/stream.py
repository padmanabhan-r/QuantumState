"""
QuantumState — Continuous metric streamer.

Emits one batch of fresh metrics + occasional logs every 30 seconds,
keeping the "now" window of data alive so Kibana dashboards look live.

Run in the background during demos:
    python data/stream.py

Stop with Ctrl+C.
"""

import os
import sys
import time
import random
import math
import signal
from datetime import datetime, timezone
from elasticsearch import Elasticsearch
from dotenv import load_dotenv

load_dotenv()

SERVICES = [
    {"name": "payment-service",   "region": "us-east-1"},
    {"name": "checkout-service",  "region": "us-east-1"},
    {"name": "auth-service",      "region": "us-west-2"},
    {"name": "inventory-service", "region": "eu-west-1"},
]

BASELINES = {
    "memory_percent":     {"mean": 52, "std": 4},
    "cpu_percent":        {"mean": 35, "std": 8},
    "error_rate":         {"mean": 0.4, "std": 0.2},
    "request_latency_ms": {"mean": 120, "std": 25},
    "requests_per_min":   {"mean": 850, "std": 120},
}

METRIC_UNITS = {
    "memory_percent":     "percent",
    "cpu_percent":        "percent",
    "error_rate":         "errors_per_min",
    "request_latency_ms": "ms",
    "requests_per_min":   "requests_per_min",
}

INTERVAL_SECONDS = 30

running = True

def handle_sigint(sig, frame):
    global running
    print("\nStopping streamer...")
    running = False

signal.signal(signal.SIGINT, handle_sigint)


def connect() -> Elasticsearch:
    cloud_id = os.getenv("ELASTIC_CLOUD_ID")
    api_key  = os.getenv("ELASTIC_API_KEY")
    if not cloud_id or not api_key:
        sys.exit("ERROR: Set ELASTIC_CLOUD_ID and ELASTIC_API_KEY in .env")
    es = Elasticsearch(cloud_id=cloud_id, api_key=api_key, request_timeout=30)
    es.info()
    return es


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def emit_metrics(es: Elasticsearch):
    now = datetime.now(timezone.utc)
    hour_offset = now.hour + now.minute / 60
    diurnal_factor = math.sin(math.pi * hour_offset / 12)

    docs = []
    for svc in SERVICES:
        for metric, cfg in BASELINES.items():
            diurnal = diurnal_factor * cfg["std"] * 0.5
            value = random.gauss(cfg["mean"] + diurnal, cfg["std"])

            if metric in ("memory_percent", "cpu_percent"):
                value = clamp(value, 5, 95)
            elif metric == "error_rate":
                value = clamp(value, 0, 5)
            elif metric == "request_latency_ms":
                value = clamp(value, 10, 2000)
            else:
                value = clamp(value, 0, 5000)

            docs.append({
                "_index": "metrics-quantumstate",
                "_source": {
                    "@timestamp":  now.isoformat(),
                    "service":     svc["name"],
                    "region":      svc["region"],
                    "metric_type": metric,
                    "value":       round(value, 2),
                    "unit":        METRIC_UNITS[metric],
                }
            })

    # Occasional INFO log (1-in-3 chance per tick)
    if random.random() < 0.33:
        svc = random.choice(SERVICES)
        docs.append({
            "_index": "logs-quantumstate",
            "_source": {
                "@timestamp": now.isoformat(),
                "service":    svc["name"],
                "region":     svc["region"],
                "level":      "INFO",
                "message":    random.choice([
                    "Health check passed",
                    "Request processed successfully",
                    f"Cache hit ratio: {random.uniform(88, 99):.1f}%",
                    f"DB pool: {random.randint(5, 30)}/100 active",
                ]),
                "trace_id":   f"trace-{random.randint(100000, 999999)}",
                "error_code": None,
            }
        })

    es.bulk(operations=[
        op for doc in docs
        for op in [{"index": {"_index": doc["_index"]}}, doc["_source"]]
    ])
    return len(docs)


if __name__ == "__main__":
    es = connect()
    print(f"Streaming metrics every {INTERVAL_SECONDS}s — Ctrl+C to stop\n")
    tick = 0
    while running:
        tick += 1
        count = emit_metrics(es)
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        print(f"[{ts}] tick {tick:>4} — {count} docs indexed")
        time.sleep(INTERVAL_SECONDS)

    print("Streamer stopped.")
