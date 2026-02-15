"""
QuantumState — Simulated microservice container.
Reports memory as % of a simulated 512MB container limit.
Emits realistic error logs to logs-quantumstate when a fault is active,
so Archaeologist has evidence to build a root cause chain.
"""
import os
import time
import threading
import random
import datetime as dt
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from elasticsearch import Elasticsearch

SERVICE_NAME           = os.getenv("SERVICE_NAME", "unknown-service")
SERVICE_PORT           = int(os.getenv("SERVICE_PORT", "8001"))
CONTAINER_MEM_LIMIT_MB = int(os.getenv("CONTAINER_MEM_LIMIT_MB", "512"))

# ES client — same pattern as rest of project
_es_cloud_id = os.getenv("ELASTIC_CLOUD_ID")
_es_api_key  = os.getenv("ELASTIC_API_KEY")
_es = Elasticsearch(cloud_id=_es_cloud_id, api_key=_es_api_key) if _es_cloud_id and _es_api_key else None

# Stable baseline memory at startup: 35–45% of container limit
_BASE_MEM_MB  = CONTAINER_MEM_LIMIT_MB * random.uniform(0.35, 0.45)
_CHUNK_MB     = 4
_LEAK_INTERVAL = 5   # seconds between allocations

app = FastAPI(title=f"QuantumState — {SERVICE_NAME}")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# --- Fault state ---
_fault: dict      = {"type": None, "active": False}
_leak_chunks: list = []
_start_time        = time.time()

# --- Log message templates per fault type ---
_LEAK_LOGS = [
    ("ERROR",    "HEAP_PRESSURE",         "JVM heap elevated: {mem:.0f}% — connection pool under pressure"),
    ("WARN",     "GC_OVERHEAD",           "GC overhead limit approaching: {mem:.0f}% heap utilised"),
    ("ERROR",    "CONN_POOL_EXHAUSTED",   "Connection pool exhausted — unable to acquire connection within 5000ms"),
    ("CRITICAL", "OOM_IMMINENT",          "Out-of-memory condition imminent: {mem:.0f}% heap, GC unable to reclaim"),
    ("WARN",     "MEMORY_LEAK_DETECTED",  "Heap growth rate 1.9%/min — possible memory leak in payment processor"),
]
_SPIKE_LOGS = [
    ("ERROR",    "REQUEST_TIMEOUT",       "Upstream timeout after 1200ms — Redis eviction in progress"),
    ("ERROR",    "CACHE_MISS",            "Cache miss rate 94% — Redis maxmemory policy evicting keys"),
    ("CRITICAL", "ERROR_RATE_CRITICAL",   "Error rate {err:.0f}/min exceeds SLA threshold of 5/min"),
    ("WARN",     "LATENCY_DEGRADED",      "p99 latency {lat:.0f}ms — dependency degradation detected"),
]


def _ts() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _emit_logs(fault_type: str):
    """Write realistic error logs to logs-quantumstate via ES client."""
    if not _es:
        return
    mem = _current_mem_percent()
    err = random.uniform(15, 25)
    lat = random.uniform(800, 1400)
    templates = _LEAK_LOGS if fault_type == "leak" else _SPIKE_LOGS
    for lvl, code, msg_tmpl in random.sample(templates, k=min(3, len(templates))):
        doc = {
            "@timestamp": _ts(),
            "service":    SERVICE_NAME,
            "level":      lvl,
            "error_code": code,
            "message":    msg_tmpl.format(mem=mem, err=err, lat=lat),
            "region":     "us-east-1",
            "source":     "real",
        }
        try:
            _es.index(index="logs-quantumstate", document=doc)
        except Exception:
            pass


def _run_leak():
    """Allocate 4MB every 5s and emit error logs every 30s."""
    log_counter = 0
    while _fault["active"] and _fault["type"] == "leak":
        _leak_chunks.append(b"x" * _CHUNK_MB * 1024 * 1024)
        log_counter += 1
        if log_counter % 6 == 0:   # every ~30s emit logs
            threading.Thread(target=_emit_logs, args=("leak",), daemon=True).start()
        time.sleep(_LEAK_INTERVAL)


def _current_mem_percent() -> float:
    leak_mb  = len(_leak_chunks) * _CHUNK_MB
    used_mb  = _BASE_MEM_MB + leak_mb + random.uniform(-1, 1)
    return round(min((used_mb / CONTAINER_MEM_LIMIT_MB) * 100, 99.9), 2)


# --- Endpoints ---

@app.get("/health")
def health():
    mem      = _current_mem_percent()
    is_spike = _fault["active"] and _fault["type"] == "spike"
    return {
        "status":         "degraded" if _fault["active"] else "healthy",
        "service":        SERVICE_NAME,
        "memory_percent": mem,
        "cpu_percent":    round(random.uniform(30, 55) if is_spike else random.uniform(5, 20), 2),
        "error_rate":     round(random.uniform(15, 25) if is_spike else random.uniform(0, 0.5), 2),
        "latency_ms":     round(random.uniform(800, 1400) if is_spike else random.uniform(40, 120), 1),
        "fault":          _fault["type"],
        "uptime_seconds": round(time.time() - _start_time, 1),
    }


@app.post("/simulate/leak")
def inject_leak():
    if _fault["active"]:
        return {"ok": False, "msg": "fault already active"}
    _fault["type"]   = "leak"
    _fault["active"] = True
    # Emit first batch of logs immediately
    threading.Thread(target=_emit_logs, args=("leak",), daemon=True).start()
    threading.Thread(target=_run_leak, daemon=True).start()
    return {"ok": True, "fault": "leak", "service": SERVICE_NAME}


@app.post("/simulate/spike")
def inject_spike(duration: int = 120):
    _fault["type"]   = "spike"
    _fault["active"] = True
    threading.Thread(target=_emit_logs, args=("spike",), daemon=True).start()
    def _auto_reset():
        time.sleep(duration)
        _fault["active"] = False
        _fault["type"]   = None
    threading.Thread(target=_auto_reset, daemon=True).start()
    return {"ok": True, "fault": "spike", "duration_seconds": duration, "service": SERVICE_NAME}


@app.post("/simulate/reset")
def reset_fault():
    global _leak_chunks
    _fault["active"] = False
    _fault["type"]   = None
    _leak_chunks     = []
    return {"ok": True, "service": SERVICE_NAME, "memory_percent": _current_mem_percent()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=SERVICE_PORT)
