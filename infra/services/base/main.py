"""
QuantumState — Simulated microservice container.
Reports memory as % of a simulated 512MB container limit so leaks
are visible to Cassandra. Fault injection endpoints trigger real
memory allocation or error/latency spikes.
"""
import os
import time
import threading
import random
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

SERVICE_NAME = os.getenv("SERVICE_NAME", "unknown-service")
SERVICE_PORT = int(os.getenv("SERVICE_PORT", "8001"))

# Simulated container memory limit (default 512 MB)
CONTAINER_MEM_LIMIT_MB = int(os.getenv("CONTAINER_MEM_LIMIT_MB", "512"))

# Stable baseline memory at startup: 35–45% of limit
_BASE_MEM_MB = CONTAINER_MEM_LIMIT_MB * random.uniform(0.35, 0.45)

app = FastAPI(title=f"QuantumState — {SERVICE_NAME}")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# --- Fault state ---
_fault: dict = {"type": None, "active": False}
_leak_chunks: list = []
_start_time = time.time()


def _run_leak():
    """Allocate 8 MB every 2 s until reset — pushes memory ~2.4%/min on a 512MB limit."""
    while _fault["active"] and _fault["type"] == "leak":
        _leak_chunks.append(b"x" * 8 * 1024 * 1024)
        time.sleep(2)


def _current_mem_percent() -> float:
    """
    Report memory as % of the simulated container limit.
    Base + allocated leak chunks + small random jitter.
    """
    leak_mb = len(_leak_chunks) * 8
    used_mb = _BASE_MEM_MB + leak_mb + random.uniform(-1, 1)
    return round(min((used_mb / CONTAINER_MEM_LIMIT_MB) * 100, 99.9), 2)


# --- Endpoints ---

@app.get("/health")
def health():
    mem = _current_mem_percent()
    is_spike = _fault["active"] and _fault["type"] == "spike"
    return {
        "status":          "degraded" if _fault["active"] else "healthy",
        "service":         SERVICE_NAME,
        "memory_percent":  mem,
        "cpu_percent":     round(random.uniform(30, 55) if is_spike else random.uniform(5, 20), 2),
        "error_rate":      round(random.uniform(15, 25) if is_spike else random.uniform(0, 0.5), 2),
        "latency_ms":      round(random.uniform(800, 1400) if is_spike else random.uniform(40, 120), 1),
        "fault":           _fault["type"],
        "uptime_seconds":  round(time.time() - _start_time, 1),
    }


@app.post("/simulate/leak")
def inject_leak():
    if _fault["active"]:
        return {"ok": False, "msg": "fault already active"}
    _fault["type"] = "leak"
    _fault["active"] = True
    threading.Thread(target=_run_leak, daemon=True).start()
    return {"ok": True, "fault": "leak", "service": SERVICE_NAME}


@app.post("/simulate/spike")
def inject_spike(duration: int = 120):
    _fault["type"] = "spike"
    _fault["active"] = True
    def _auto_reset():
        time.sleep(duration)
        _fault["active"] = False
        _fault["type"] = None
    threading.Thread(target=_auto_reset, daemon=True).start()
    return {"ok": True, "fault": "spike", "duration_seconds": duration, "service": SERVICE_NAME}


@app.post("/simulate/reset")
def reset_fault():
    global _leak_chunks
    _fault["active"] = False
    _fault["type"] = None
    _leak_chunks = []
    return {"ok": True, "service": SERVICE_NAME, "memory_percent": _current_mem_percent()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=SERVICE_PORT)
