"""POST /api/sim/* — Simulation Control endpoints."""
import os
import sys
import math
import random
import threading
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from inject import inject_memory_leak, inject_deployment_rollback, inject_error_spike
from elastic import get_es

router = APIRouter(prefix="/sim", tags=["sim"])

# ── Shared streamer state ──────────────────────────────────────────────────────

_stream_thread: threading.Thread | None = None
_stream_stop:   threading.Event  | None = None
_stream_lock = threading.Lock()

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

QUANTUMSTATE_INDICES = {
    "metrics-quantumstate": {
        "mappings": {"properties": {
            "@timestamp": {"type": "date"}, "service": {"type": "keyword"},
            "region": {"type": "keyword"}, "metric_type": {"type": "keyword"},
            "value": {"type": "double"}, "unit": {"type": "keyword"},
        }}
    },
    "logs-quantumstate": {
        "mappings": {"properties": {
            "@timestamp": {"type": "date"}, "service": {"type": "keyword"},
            "region": {"type": "keyword"}, "level": {"type": "keyword"},
            "message": {"type": "text"}, "trace_id": {"type": "keyword"},
            "error_code": {"type": "keyword"},
        }}
    },
    "incidents-quantumstate": {
        "mappings": {"properties": {
            "@timestamp":         {"type": "date"},
            "service":            {"type": "keyword"},
            "region":             {"type": "keyword"},
            "anomaly_type":       {"type": "keyword"},
            "root_cause":         {"type": "text"},
            "action_taken":       {"type": "text"},
            "recommended_action": {"type": "keyword"},
            "confidence_score":   {"type": "float"},
            "risk_level":         {"type": "keyword"},
            "resolved_at":        {"type": "date"},
            "mttr_seconds":       {"type": "integer"},
            "mttr_estimate":      {"type": "keyword"},
            "status":             {"type": "keyword"},
            "resolution_status":  {"type": "keyword"},
            "pipeline_run":       {"type": "boolean"},
            "pipeline_summary":   {"type": "text"},
            "guardian_verified":  {"type": "boolean"},
            "lessons_learned":    {"type": "text"},
        }}
    },
    "agent-decisions-quantumstate": {
        "mappings": {"properties": {
            "@timestamp": {"type": "date"}, "agent": {"type": "keyword"},
            "decision": {"type": "text"}, "confidence": {"type": "integer"},
            "service": {"type": "keyword"},
            "context": {"type": "object", "enabled": False},
        }}
    },
    "remediation-actions-quantumstate": {
        "mappings": {"properties": {
            "@timestamp":      {"type": "date"},
            "incident_id":     {"type": "keyword"},
            "service":         {"type": "keyword"},
            "action":          {"type": "keyword"},
            "anomaly_type":    {"type": "keyword"},
            "confidence_score":{"type": "float"},
            "risk_level":      {"type": "keyword"},
            "triggered_by":    {"type": "keyword"},
            "status":          {"type": "keyword"},
            "exec_id":         {"type": "keyword"},
            "executed_at":     {"type": "date"},
            "workflow_triggered": {"type": "boolean"},
            "case_id":         {"type": "keyword"},
            "root_cause":      {"type": "text"},
        }}
    },
    "remediation-results-quantumstate": {
        "mappings": {"properties": {
            "@timestamp":      {"type": "date"},
            "incident_id":     {"type": "keyword"},
            "service":         {"type": "keyword"},
            "action":          {"type": "keyword"},
            "exec_id":         {"type": "keyword"},
            "outcome":         {"type": "keyword"},
            "recovery_initiated": {"type": "boolean"},
        }}
    },
    "approval-requests-quantumstate": {
        "mappings": {"properties": {
            "@timestamp":       {"type": "date"},
            "incident_id":      {"type": "keyword"},
            "service":          {"type": "keyword"},
            "proposed_action":  {"type": "keyword"},
            "reason":           {"type": "text"},
            "evidence_summary": {"type": "text"},
            "confidence_score": {"type": "float"},
            "status":           {"type": "keyword"},
            "resolved_by":      {"type": "keyword"},
            "resolved_at":      {"type": "date"},
        }}
    },
}

PAST_INCIDENTS = [
    {
        "service": "payment-service", "region": "us-east-1",
        "anomaly_type": "memory_leak_progressive",
        "root_cause": "Memory leak in JDBC connection pool introduced by deploy v2.1.0.",
        "action_taken": "Rolled back to v2.0.9. Memory stabilised at 52%.",
        "mttr_seconds": 2820, "days_ago": 14,
    },
    {
        "service": "auth-service", "region": "us-west-2",
        "anomaly_type": "error_spike_sudden",
        "root_cause": "Redis session cache became unavailable. Auth fell back to DB lookups.",
        "action_taken": "Restarted Redis cluster. Scaled DB connection pool.",
        "mttr_seconds": 960, "days_ago": 7,
    },
    {
        "service": "checkout-service", "region": "us-east-1",
        "anomaly_type": "deployment_regression",
        "root_cause": "Deploy v3.4.2 introduced unhandled NPE in cart serialisation.",
        "action_taken": "Immediate rollback to v3.4.1.",
        "mttr_seconds": 480, "days_ago": 3,
    },
    {
        "service": "inventory-service", "region": "eu-west-1",
        "anomaly_type": "memory_leak_progressive",
        "root_cause": "Unbounded in-memory cache for product catalogue.",
        "action_taken": "Added LRU eviction. Deployed hotfix v1.8.3.",
        "mttr_seconds": 5400, "days_ago": 21,
    },
]


def _stream_loop(es, stop_event: threading.Event):
    while not stop_event.is_set():
        now = datetime.now(timezone.utc)
        diurnal = math.sin(math.pi * (now.hour + now.minute / 60) / 12)
        docs = []
        for svc in SERVICES:
            for metric, cfg in BASELINES.items():
                v = random.gauss(cfg["mean"] + diurnal * cfg["std"] * 0.5, cfg["std"])
                v = max(5, min(95, v)) if metric in ("memory_percent", "cpu_percent") else max(0, min(5, v))
                docs.append({
                    "@timestamp": now.isoformat(), "service": svc["name"],
                    "region": svc["region"], "metric_type": metric,
                    "value": round(v, 2), "unit": METRIC_UNITS[metric],
                })
        try:
            es.bulk(operations=[op for d in docs for op in [{"index": {"_index": "metrics-quantumstate"}}, d]])
        except Exception:
            pass
        stop_event.wait(30)


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/status")
def get_status():
    global _stream_thread
    with _stream_lock:
        streaming = _stream_thread is not None and _stream_thread.is_alive()
    es = get_es()
    indices = {}
    for name in QUANTUMSTATE_INDICES:
        try:
            exists = es.indices.exists(index=name)
            count = es.count(index=name)["count"] if exists else 0
            indices[name] = {"exists": bool(exists), "count": count}
        except Exception:
            indices[name] = {"exists": False, "count": 0}
    return {"streaming": streaming, "indices": indices}


@router.post("/setup")
def run_setup():
    from elasticsearch import helpers

    es = get_es()

    def clamp(v, lo, hi): return max(lo, min(hi, v))

    # Create indices
    for name, body in QUANTUMSTATE_INDICES.items():
        if not es.indices.exists(index=name):
            es.indices.create(index=name, body=body)

    # 24h baseline metrics
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=24)
    docs, t = [], start
    while t <= now:
        for svc in SERVICES:
            diurnal = math.sin(math.pi * (t.hour + t.minute / 60) / 12)
            for metric, cfg in BASELINES.items():
                v = random.gauss(cfg["mean"] + diurnal * cfg["std"] * 0.5, cfg["std"])
                if metric in ("memory_percent", "cpu_percent"):
                    v = clamp(v, 5, 95)
                elif metric == "error_rate":
                    v = clamp(v, 0, 5)
                elif metric == "request_latency_ms":
                    v = clamp(v, 10, 2000)
                else:
                    v = clamp(v, 0, 5000)
                docs.append({"_index": "metrics-quantumstate", "_source": {
                    "@timestamp": t.isoformat(), "service": svc["name"],
                    "region": svc["region"], "metric_type": metric,
                    "value": round(v, 2), "unit": METRIC_UNITS[metric],
                }})
        t += timedelta(minutes=1)

    for _ in helpers.parallel_bulk(es, docs, chunk_size=2000, thread_count=4,
                                   raise_on_error=False, raise_on_exception=False):
        pass

    # Baseline logs
    log_docs, t = [], start
    INFO_MSGS = [
        "Request processed successfully", "Health check passed",
        "Cache hit ratio: {:.1f}%", "DB pool: {}/100 active",
        "Metrics flushed to collector", "Config refreshed",
    ]
    while t <= now:
        for svc in SERVICES:
            msg = random.choice(INFO_MSGS).format(random.uniform(85, 99), random.randint(5, 30))
            log_docs.append({"_index": "logs-quantumstate", "_source": {
                "@timestamp": t.isoformat(), "service": svc["name"],
                "region": svc["region"], "level": "INFO", "message": msg,
                "trace_id": f"trace-{random.randint(100000, 999999)}", "error_code": None,
            }})
        t += timedelta(minutes=5)

    for _ in helpers.parallel_bulk(es, log_docs, chunk_size=2000,
                                   raise_on_error=False, raise_on_exception=False):
        pass

    # Seed incidents
    inc_docs = []
    for inc in PAST_INCIDENTS:
        ts = now - timedelta(days=inc["days_ago"])
        inc_docs.append({"_index": "incidents-quantumstate", "_source": {
            "@timestamp": ts.isoformat(), "service": inc["service"],
            "region": inc["region"], "anomaly_type": inc["anomaly_type"],
            "root_cause": inc["root_cause"], "action_taken": inc["action_taken"],
            "resolved_at": (ts + timedelta(seconds=inc["mttr_seconds"])).isoformat(),
            "mttr_seconds": inc["mttr_seconds"], "status": "resolved",
            "resolution_status": "RESOLVED",
            "pipeline_run": True,
            "guardian_verified": True,
        }})
    es.bulk(operations=[op for d in inc_docs for op in [{"index": {"_index": d["_index"]}}, d["_source"]]])

    for idx in QUANTUMSTATE_INDICES:
        es.indices.refresh(index=idx)

    return {"ok": True, "metric_docs": len(docs), "log_docs": len(log_docs), "incidents": len(inc_docs)}


@router.post("/stream/start")
def start_stream():
    global _stream_thread, _stream_stop
    with _stream_lock:
        if _stream_thread and _stream_thread.is_alive():
            return {"ok": True, "streaming": True, "note": "already running"}
        es = get_es()
        stop_event = threading.Event()
        t = threading.Thread(target=_stream_loop, args=(es, stop_event), daemon=True)
        t.start()
        _stream_thread = t
        _stream_stop = stop_event
    return {"ok": True, "streaming": True}


@router.post("/stream/stop")
def stop_stream():
    global _stream_thread, _stream_stop
    with _stream_lock:
        if _stream_stop:
            _stream_stop.set()
        if _stream_thread:
            _stream_thread.join(timeout=5)
        _stream_thread = None
        _stream_stop = None
    return {"ok": True, "streaming": False}


@router.post("/inject/{scenario}")
def inject_scenario(scenario: str):
    es = get_es()
    mapping = {
        "memory_leak":          inject_memory_leak,
        "deployment_rollback":  inject_deployment_rollback,
        "error_spike":          inject_error_spike,
    }
    fn = mapping.get(scenario)
    if not fn:
        return {"ok": False, "error": f"Unknown scenario: {scenario}"}
    try:
        fn(es)
        return {"ok": True, "scenario": scenario}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@router.post("/cleanup/incidents")
def clear_incidents():
    """Delete all incident, remediation, and guardian result docs — keeps metrics/logs intact."""
    es = get_es()
    results = {}
    for name in [
        "incidents-quantumstate",
        "remediation-actions-quantumstate",
        "remediation-results-quantumstate",
        "approval-requests-quantumstate",
        "agent-decisions-quantumstate",
    ]:
        try:
            if es.indices.exists(index=name):
                es.delete_by_query(index=name, body={"query": {"match_all": {}}}, refresh=True)
                results[name] = "cleared"
            else:
                results[name] = "not found"
        except Exception as exc:
            results[name] = f"error: {exc}"
    return {"ok": True, "results": results}


@router.post("/cleanup/clear")
def clear_data():
    es = get_es()
    results = {}
    for name in QUANTUMSTATE_INDICES:
        try:
            if es.indices.exists(index=name):
                es.delete_by_query(index=name, body={"query": {"match_all": {}}}, refresh=True)
                results[name] = "cleared"
            else:
                results[name] = "not found"
        except Exception as exc:
            results[name] = f"error: {exc}"
    return {"ok": True, "results": results}


@router.post("/cleanup/delete-indices")
def delete_indices():
    es = get_es()
    results = {}
    for name in QUANTUMSTATE_INDICES:
        try:
            if es.indices.exists(index=name):
                es.indices.delete(index=name)
                results[name] = "deleted"
            else:
                results[name] = "not found"
        except Exception as exc:
            results[name] = f"error: {exc}"
    return {"ok": True, "results": results}
