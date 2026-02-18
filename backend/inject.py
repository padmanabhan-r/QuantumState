"""
QuantumState — Anomaly scenario injector.

Bulk-loads an anomaly pattern backdated ~25 minutes so Cassandra's
ES|QL queries detect it immediately on the next agent run.

Usage:
    python data/inject.py memory-leak
    python data/inject.py deployment-rollback
    python data/inject.py error-spike

Scenarios:
  memory-leak         — payment-service, gradual memory ramp over 25 min
  deployment-rollback — checkout-service, sudden error spike after a deploy event
  error-spike         — auth-service, sharp error rate jump
"""

import os
import sys
import random
import math
from datetime import datetime, timezone, timedelta
from elasticsearch import Elasticsearch, helpers
from dotenv import load_dotenv

load_dotenv()


def connect() -> Elasticsearch:
    cloud_id = os.getenv("ELASTIC_CLOUD_ID")
    api_key  = os.getenv("ELASTIC_API_KEY")
    if not cloud_id or not api_key:
        sys.exit("ERROR: Set ELASTIC_CLOUD_ID and ELASTIC_API_KEY in .env")
    es = Elasticsearch(cloud_id=cloud_id, api_key=api_key, request_timeout=60)
    info = es.info()
    print(f"Connected: {info['cluster_name']}")
    return es


def bulk_index(es: Elasticsearch, docs: list):
    success, errors = 0, 0
    for ok, _ in helpers.parallel_bulk(
        es, docs, chunk_size=1000,
        raise_on_error=False, raise_on_exception=False,
    ):
        if ok: success += 1
        else:  errors += 1
    return success, errors


# ---------------------------------------------------------------------------
# Scenario 1: Memory Leak — payment-service
# ---------------------------------------------------------------------------

def inject_memory_leak(es: Elasticsearch):
    """
    Gradual memory ramp from ~55% to ~89% over 25 minutes.
    At 80%+, error_rate starts climbing. Logs emit warnings at 75%+.
    """
    SERVICE = "payment-service"
    REGION  = "us-east-1"
    MINUTES = 25
    now     = datetime.now(timezone.utc)
    start   = now - timedelta(minutes=MINUTES)

    docs = []
    for i in range(MINUTES * 3):  # 3 data points per minute for stronger signal
        t = start + timedelta(seconds=i * 20)
        progress = (i / 3) / MINUTES  # 0.0 → 1.0

        # Memory climbs from 55% to 89%
        memory = 55 + (34 * progress) + random.gauss(0, 1)
        # CPU slightly elevated
        cpu = 35 + (12 * progress) + random.gauss(0, 3)
        # Error rate starts climbing after memory > 80%
        error_rate = 0.4 + (max(0, memory - 80) * 0.3) + random.gauss(0, 0.1)
        # Latency degrades with memory
        latency = 120 + (200 * progress ** 2) + random.gauss(0, 15)
        # Requests drop slightly (clients timing out)
        requests = 850 - (150 * progress) + random.gauss(0, 30)

        for metric, value, unit in [
            ("memory_percent",     memory,     "percent"),
            ("cpu_percent",        cpu,         "percent"),
            ("error_rate",         error_rate,  "errors_per_min"),
            ("latency_ms", latency,     "ms"),
            ("requests_per_min",   requests,    "requests_per_min"),
        ]:
            docs.append({
                "_index": "metrics-quantumstate",
                "_source": {
                    "@timestamp":  t.isoformat(),
                    "service":     SERVICE,
                    "region":      REGION,
                    "metric_type": metric,
                    "value":       round(max(0, value), 2),
                    "unit":        unit,
                }
            })

        # Log warnings as memory climbs
        if memory > 85:
            level, msg = "ERROR", f"JVM heap critical: {memory:.1f}% — GC overhead limit approaching"
        elif memory > 75:
            level, msg = "WARN", f"JVM heap elevated: {memory:.1f}% — connection pool under pressure"
        elif memory > 65:
            level, msg = "WARN", f"Memory usage elevated: {memory:.1f}% — monitoring closely"
        else:
            continue  # No log needed for normal range

        docs.append({
            "_index": "logs-quantumstate",
            "_source": {
                "@timestamp": t.isoformat(),
                "service":    SERVICE,
                "region":     REGION,
                "level":      level,
                "message":    msg,
                "trace_id":   f"trace-{random.randint(100000, 999999)}",
                "error_code": "HEAP_PRESSURE" if memory > 80 else None,
            }
        })

    success, errors = bulk_index(es, docs)
    es.indices.refresh(index="metrics-quantumstate")
    es.indices.refresh(index="logs-quantumstate")
    print(f"  Injected memory-leak on {SERVICE}: {success} docs ({errors} errors)")
    print(f"  Memory ramped {55}% → ~89% over {MINUTES} minutes (backdated)")
    print(f"  Cassandra should detect this immediately.")


# ---------------------------------------------------------------------------
# Scenario 2: Deployment Rollback — checkout-service
# ---------------------------------------------------------------------------

def inject_deployment_rollback(es: Elasticsearch):
    """
    Deploy event at T-20min, followed by immediate error spike.
    Error rate jumps from 0.4 to ~18 within 3 minutes of deploy.
    """
    SERVICE = "checkout-service"
    REGION  = "us-east-1"
    MINUTES = 25
    DEPLOY_AT_MIN = 5  # deploy happens 5 minutes into the window
    now   = datetime.now(timezone.utc)
    start = now - timedelta(minutes=MINUTES)

    docs = []

    # Deploy log event
    deploy_time = start + timedelta(minutes=DEPLOY_AT_MIN)
    docs.append({
        "_index": "logs-quantumstate",
        "_source": {
            "@timestamp": deploy_time.isoformat(),
            "service":    SERVICE,
            "region":     REGION,
            "level":      "INFO",
            "message":    "Deployment v3.5.0 started — rolling update initiated",
            "trace_id":   "trace-deploy-350",
            "error_code": None,
        }
    })
    docs.append({
        "_index": "logs-quantumstate",
        "_source": {
            "@timestamp": (deploy_time + timedelta(seconds=45)).isoformat(),
            "service":    SERVICE,
            "region":     REGION,
            "level":      "INFO",
            "message":    "Deployment v3.5.0 complete — all pods running",
            "trace_id":   "trace-deploy-350",
            "error_code": None,
        }
    })

    for i in range(MINUTES):
        t = start + timedelta(minutes=i)
        mins_since_deploy = i - DEPLOY_AT_MIN

        if mins_since_deploy < 0:
            # Normal pre-deploy
            error_rate = 0.4 + random.gauss(0, 0.15)
            latency    = 120 + random.gauss(0, 20)
            cpu        = 35 + random.gauss(0, 6)
            memory     = 52 + random.gauss(0, 3)
        else:
            # Post-deploy spike: error rate rockets in first 3 min, stays high
            ramp = min(1.0, mins_since_deploy / 3)
            error_rate = 0.4 + (18 * ramp) + random.gauss(0, 0.5)
            latency    = 120 + (800 * ramp) + random.gauss(0, 40)
            cpu        = 35 + (30 * ramp) + random.gauss(0, 5)
            memory     = 52 + (8 * ramp) + random.gauss(0, 3)

            # Error logs after deploy
            if mins_since_deploy >= 1 and random.random() < 0.8:
                docs.append({
                    "_index": "logs-quantumstate",
                    "_source": {
                        "@timestamp": t.isoformat(),
                        "service":    SERVICE,
                        "region":     REGION,
                        "level":      "ERROR",
                        "message":    random.choice([
                            "NullPointerException in CartSerialiser.serialise() — cart_id missing",
                            "HTTP 500: Unhandled exception in /api/checkout — see stack trace",
                            "Cart serialisation failed: field 'discount_code' is null",
                            "Internal server error on POST /checkout — deploy v3.5.0 suspect",
                        ]),
                        "trace_id":   f"trace-{random.randint(100000, 999999)}",
                        "error_code": "INTERNAL_SERVER_ERROR",
                    }
                })

        for metric, value, unit in [
            ("memory_percent",     memory,     "percent"),
            ("cpu_percent",        cpu,         "percent"),
            ("error_rate",         error_rate,  "errors_per_min"),
            ("latency_ms", latency,     "ms"),
            ("requests_per_min",   max(0, 850 - error_rate * 20), "requests_per_min"),
        ]:
            docs.append({
                "_index": "metrics-quantumstate",
                "_source": {
                    "@timestamp":  t.isoformat(),
                    "service":     SERVICE,
                    "region":      REGION,
                    "metric_type": metric,
                    "value":       round(max(0, value), 2),
                    "unit":        unit,
                }
            })

    success, errors = bulk_index(es, docs)
    es.indices.refresh(index="metrics-quantumstate")
    es.indices.refresh(index="logs-quantumstate")
    print(f"  Injected deployment-rollback on {SERVICE}: {success} docs ({errors} errors)")
    print(f"  Deploy v3.5.0 at T-{MINUTES - DEPLOY_AT_MIN}min, error rate spiked to ~18/min")
    print(f"  Archaeologist should correlate the deploy event.")


# ---------------------------------------------------------------------------
# Scenario 3: Error Spike — auth-service
# ---------------------------------------------------------------------------

def inject_error_spike(es: Elasticsearch):
    """
    Sudden, sharp error rate jump on auth-service at T-15min.
    Error rate goes from 0.3 to 28 in under 2 minutes.
    Caused by Redis cache failure (visible in logs).
    """
    SERVICE  = "auth-service"
    REGION   = "us-west-2"
    MINUTES  = 20
    SPIKE_AT = 5  # spike happens 5 minutes into the window
    now   = datetime.now(timezone.utc)
    start = now - timedelta(minutes=MINUTES)

    docs = []

    for i in range(MINUTES):
        t = start + timedelta(minutes=i)
        mins_since_spike = i - SPIKE_AT

        if mins_since_spike < 0:
            error_rate = 0.3 + random.gauss(0, 0.1)
            latency    = 95 + random.gauss(0, 15)
            cpu        = 28 + random.gauss(0, 5)
            memory     = 48 + random.gauss(0, 3)
        else:
            # Sharp spike, stays high
            error_rate = 28 + random.gauss(0, 2)
            latency    = 95 + (1200 * min(1, mins_since_spike / 2)) + random.gauss(0, 50)
            cpu        = 28 + (45 * min(1, mins_since_spike / 2)) + random.gauss(0, 5)
            memory     = 48 + random.gauss(0, 3)

            # Redis error logs
            if random.random() < 0.9:
                docs.append({
                    "_index": "logs-quantumstate",
                    "_source": {
                        "@timestamp": t.isoformat(),
                        "service":    SERVICE,
                        "region":     REGION,
                        "level":      "ERROR",
                        "message":    random.choice([
                            "Redis connection refused — session cache unavailable",
                            "Failed to validate session token: cache miss, DB fallback timeout",
                            "Authentication failed: Redis ECONNREFUSED 127.0.0.1:6379",
                            "Session lookup fell back to DB — connection pool exhausted (100/100)",
                            "JWT validation error: token store unreachable",
                        ]),
                        "trace_id":   f"trace-{random.randint(100000, 999999)}",
                        "error_code": "REDIS_UNAVAILABLE",
                    }
                })

        # Redis failure log at spike moment
        if mins_since_spike == 0:
            docs.append({
                "_index": "logs-quantumstate",
                "_source": {
                    "@timestamp": t.isoformat(),
                    "service":    SERVICE,
                    "region":     REGION,
                    "level":      "CRITICAL",
                    "message":    "Redis cluster node evicted — session cache OFFLINE. "
                                  "Falling back to DB-backed auth. High latency expected.",
                    "trace_id":   "trace-redis-evict",
                    "error_code": "CACHE_OFFLINE",
                }
            })

        for metric, value, unit in [
            ("memory_percent",     memory,     "percent"),
            ("cpu_percent",        cpu,         "percent"),
            ("error_rate",         error_rate,  "errors_per_min"),
            ("latency_ms", latency,     "ms"),
            ("requests_per_min",   max(0, 700 - error_rate * 5), "requests_per_min"),
        ]:
            docs.append({
                "_index": "metrics-quantumstate",
                "_source": {
                    "@timestamp":  t.isoformat(),
                    "service":     SERVICE,
                    "region":      REGION,
                    "metric_type": metric,
                    "value":       round(max(0, value), 2),
                    "unit":        unit,
                }
            })

    success, errors = bulk_index(es, docs)
    es.indices.refresh(index="metrics-quantumstate")
    es.indices.refresh(index="logs-quantumstate")
    print(f"  Injected error-spike on {SERVICE}: {success} docs ({errors} errors)")
    print(f"  Error rate: 0.3 → ~28/min at T-{MINUTES - SPIKE_AT}min (Redis cache failure)")
    print(f"  Archaeologist should find the Redis CACHE_OFFLINE log.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

SCENARIOS = {
    "memory-leak":          inject_memory_leak,
    "deployment-rollback":  inject_deployment_rollback,
    "error-spike":          inject_error_spike,
}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in SCENARIOS:
        print(f"Usage: python data/inject.py [{' | '.join(SCENARIOS)}]")
        sys.exit(1)

    scenario = sys.argv[1]
    es = connect()
    print(f"\nInjecting scenario: {scenario}")
    SCENARIOS[scenario](es)
    print("\nDone. Run your agents now.")
