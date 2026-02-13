"""
QuantumState — One-time setup script.

Creates the four Elasticsearch indices and bulk-loads 24 hours of
healthy baseline data so Cassandra has a real baseline to compare against.

Run once before starting stream.py or inject.py.

Usage:
    python data/setup.py
"""

import os
import sys
import random
import math
from datetime import datetime, timezone, timedelta
from elasticsearch import Elasticsearch, helpers
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SERVICES = [
    {"name": "payment-service",   "region": "us-east-1"},
    {"name": "checkout-service",  "region": "us-east-1"},
    {"name": "auth-service",      "region": "us-west-2"},
    {"name": "inventory-service", "region": "eu-west-1"},
]

# Healthy baseline ranges per metric
BASELINES = {
    "memory_percent":     {"mean": 52, "std": 4},
    "cpu_percent":        {"mean": 35, "std": 8},
    "error_rate":         {"mean": 0.4, "std": 0.2},   # errors/min
    "request_latency_ms": {"mean": 120, "std": 25},
    "requests_per_min":   {"mean": 850, "std": 120},
}

INDICES = {
    "metrics-quantumstate": {
        "mappings": {
            "properties": {
                "@timestamp":   {"type": "date"},
                "service":      {"type": "keyword"},
                "region":       {"type": "keyword"},
                "metric_type":  {"type": "keyword"},
                "value":        {"type": "double"},
                "unit":         {"type": "keyword"},
            }
        }
    },
    "logs-quantumstate": {
        "mappings": {
            "properties": {
                "@timestamp":   {"type": "date"},
                "service":      {"type": "keyword"},
                "region":       {"type": "keyword"},
                "level":        {"type": "keyword"},
                "message":      {"type": "text"},
                "trace_id":     {"type": "keyword"},
                "error_code":   {"type": "keyword"},
            }
        }
    },
    "incidents-quantumstate": {
        "mappings": {
            "properties": {
                "@timestamp":       {"type": "date"},
                "service":          {"type": "keyword"},
                "region":           {"type": "keyword"},
                "anomaly_type":     {"type": "keyword"},
                "root_cause":       {"type": "text"},
                "actions_taken":    {"type": "text"},
                "resolved_at":      {"type": "date"},
                "mttr_seconds":     {"type": "integer"},
                "status":           {"type": "keyword"},
            }
        }
    },
    "agent-decisions-quantumstate": {
        "mappings": {
            "properties": {
                "@timestamp":   {"type": "date"},
                "agent":        {"type": "keyword"},
                "decision":     {"type": "text"},
                "confidence":   {"type": "integer"},
                "service":      {"type": "keyword"},
                "context":      {"type": "object", "enabled": False},
            }
        }
    },
}

# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

def connect() -> Elasticsearch:
    cloud_id = os.getenv("ELASTIC_CLOUD_ID")
    api_key  = os.getenv("ELASTIC_API_KEY")
    if not cloud_id or not api_key:
        sys.exit("ERROR: Set ELASTIC_CLOUD_ID and ELASTIC_API_KEY in .env")
    es = Elasticsearch(cloud_id=cloud_id, api_key=api_key, request_timeout=60)
    info = es.info()
    print(f"Connected: {info['cluster_name']} (ES {info['version']['number']})")
    return es

# ---------------------------------------------------------------------------
# Index setup
# ---------------------------------------------------------------------------

def setup_indices(es: Elasticsearch):
    print("\nCreating indices...")
    for name, body in INDICES.items():
        if es.indices.exists(index=name):
            print(f"  SKIP  {name}")
        else:
            es.indices.create(index=name, body=body)
            print(f"  OK    {name}")

# ---------------------------------------------------------------------------
# Baseline metric generation
# ---------------------------------------------------------------------------

def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))

def noisy(mean: float, std: float) -> float:
    return random.gauss(mean, std)

METRIC_UNITS = {
    "memory_percent":     "percent",
    "cpu_percent":        "percent",
    "error_rate":         "errors_per_min",
    "request_latency_ms": "ms",
    "requests_per_min":   "requests_per_min",
}

def generate_baseline_metrics():
    """
    Generates one metric doc per service per metric_type per minute
    for the last 24 hours. ~27,000 docs total.
    """
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=24)
    minute = timedelta(minutes=1)

    docs = []
    t = start
    while t <= now:
        for svc in SERVICES:
            for metric, cfg in BASELINES.items():
                # Add gentle sinusoidal variation (diurnal pattern)
                hour_offset = (t.hour + t.minute / 60)
                diurnal = math.sin(math.pi * hour_offset / 12) * (cfg["std"] * 0.5)
                value = noisy(cfg["mean"] + diurnal, cfg["std"])

                # Clamp to realistic bounds
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
                        "@timestamp":  t.isoformat(),
                        "service":     svc["name"],
                        "region":      svc["region"],
                        "metric_type": metric,
                        "value":       round(value, 2),
                        "unit":        METRIC_UNITS[metric],
                    }
                })
        t += minute
    return docs

# ---------------------------------------------------------------------------
# Baseline log generation (sparse — every 5 min, INFO only)
# ---------------------------------------------------------------------------

INFO_MESSAGES = [
    "Request processed successfully",
    "Cache hit ratio: {:.1f}%",
    "Health check passed",
    "Connection pool: {}/100 active",
    "Scheduled job completed in {}ms",
    "Config refreshed from remote",
    "Metrics flushed to collector",
]

def generate_baseline_logs():
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=24)
    interval = timedelta(minutes=5)

    docs = []
    t = start
    while t <= now:
        for svc in SERVICES:
            msg_template = random.choice(INFO_MESSAGES)
            msg = msg_template.format(
                random.uniform(85, 99),
                random.randint(10, 40),
                random.randint(50, 300),
            ) if "{" in msg_template else msg_template

            docs.append({
                "_index": "logs-quantumstate",
                "_source": {
                    "@timestamp": t.isoformat(),
                    "service":    svc["name"],
                    "region":     svc["region"],
                    "level":      "INFO",
                    "message":    msg,
                    "trace_id":   f"trace-{random.randint(100000, 999999)}",
                    "error_code": None,
                }
            })
        t += interval
    return docs

# ---------------------------------------------------------------------------
# Historical incidents (so Archaeologist can find_similar_incidents)
# ---------------------------------------------------------------------------

PAST_INCIDENTS = [
    {
        "service":       "payment-service",
        "region":        "us-east-1",
        "anomaly_type":  "memory_leak_progressive",
        "root_cause":    "Memory leak in JDBC connection pool introduced by deploy v2.1.0. "
                         "Connections not released after timeout, causing gradual heap exhaustion.",
        "actions_taken": "Rolled back to v2.0.9. Restarted service. Verified memory stabilised at 52%.",
        "mttr_seconds":  2820,
        "days_ago":      14,
    },
    {
        "service":       "auth-service",
        "region":        "us-west-2",
        "anomaly_type":  "error_spike_sudden",
        "root_cause":    "Redis session cache became unavailable due to node eviction. "
                         "Auth service fell back to database lookups, overwhelming DB connections.",
        "actions_taken": "Restarted Redis cluster. Scaled DB connection pool. "
                         "Added circuit breaker for cache failures.",
        "mttr_seconds":  960,
        "days_ago":      7,
    },
    {
        "service":       "checkout-service",
        "region":        "us-east-1",
        "anomaly_type":  "deployment_regression",
        "root_cause":    "Deploy v3.4.2 introduced unhandled null pointer exception in cart "
                         "serialisation logic, causing 5xx errors on all checkout requests.",
        "actions_taken": "Immediate rollback to v3.4.1. Error rate returned to baseline within 2 minutes.",
        "mttr_seconds":  480,
        "days_ago":      3,
    },
    {
        "service":       "inventory-service",
        "region":        "eu-west-1",
        "anomaly_type":  "memory_leak_progressive",
        "root_cause":    "Unbounded in-memory cache for product catalogue growing without eviction policy. "
                         "Memory grew 2% per hour under normal load.",
        "actions_taken": "Added LRU eviction policy with 10k item limit. Deployed hotfix v1.8.3.",
        "mttr_seconds":  5400,
        "days_ago":      21,
    },
]

def generate_past_incidents():
    now = datetime.now(timezone.utc)
    docs = []
    for inc in PAST_INCIDENTS:
        ts = now - timedelta(days=inc["days_ago"])
        resolved_at = ts + timedelta(seconds=inc["mttr_seconds"])
        docs.append({
            "_index": "incidents-quantumstate",
            "_source": {
                "@timestamp":    ts.isoformat(),
                "service":       inc["service"],
                "region":        inc["region"],
                "anomaly_type":  inc["anomaly_type"],
                "root_cause":    inc["root_cause"],
                "actions_taken": inc["actions_taken"],
                "resolved_at":   resolved_at.isoformat(),
                "mttr_seconds":  inc["mttr_seconds"],
                "status":        "resolved",
            }
        })
    return docs

# ---------------------------------------------------------------------------
# Bulk index
# ---------------------------------------------------------------------------

def bulk_index(es: Elasticsearch, docs: list, label: str):
    total = len(docs)
    print(f"  Indexing {total:,} {label}...", end=" ", flush=True)
    success, errors = 0, 0
    for ok, _ in helpers.parallel_bulk(
        es, docs, chunk_size=2000, thread_count=4,
        raise_on_error=False, raise_on_exception=False,
    ):
        if ok:
            success += 1
        else:
            errors += 1
    print(f"done ({success:,} ok, {errors} errors)")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    es = connect()
    setup_indices(es)

    print("\nGenerating baseline data...")
    metrics  = generate_baseline_metrics()
    logs     = generate_baseline_logs()
    incidents = generate_past_incidents()

    print(f"  {len(metrics):,} metric docs (24h × 4 services × 5 metrics)")
    print(f"  {len(logs):,} log docs")
    print(f"  {len(incidents)} past incidents")

    print("\nIndexing...")
    bulk_index(es, metrics,   "baseline metrics")
    bulk_index(es, logs,      "baseline logs")
    bulk_index(es, incidents, "past incidents")

    es.indices.refresh(index="metrics-quantumstate")
    es.indices.refresh(index="logs-quantumstate")
    es.indices.refresh(index="incidents-quantumstate")

    print("\nSetup complete. Run stream.py to keep data flowing.")
