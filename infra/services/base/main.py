"""
QuantumState — Simulated microservice container.
Exposes real memory/CPU via psutil + fault injection endpoints.
"""
import os
import time
import threading
import psutil
import random
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

SERVICE_NAME = os.getenv("SERVICE_NAME", "unknown-service")
SERVICE_PORT = int(os.getenv("SERVICE_PORT", "8001"))

app = FastAPI(title=f"QuantumState — {SERVICE_NAME}")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# --- Fault state ---
_fault: dict = {"type": None, "active": False}
_leak_chunks: list = []
_leak_thread: threading.Thread | None = None
_spike_until: float = 0.0
_start_time = time.time()


# --- Fault threads ---

def _run_leak():
    """Allocate ~2 MB every 2 seconds until fault is reset."""
    while _fault["active"] and _fault["type"] == "leak":
        _leak_chunks.append(b"x" * 2 * 1024 * 1024)
        time.sleep(2)


# --- Endpoints ---

@app.get("/health")
def health():
    proc = psutil.Process()
    mem = proc.memory_percent()
    cpu = psutil.cpu_percent(interval=0.1)
    # Simulate error_rate bump during spike fault
    error_rate = round(random.uniform(15, 25), 2) if _fault["active"] and _fault["type"] == "spike" else round(random.uniform(0, 0.5), 2)
    latency_ms = round(random.uniform(800, 1400), 1) if _fault["active"] and _fault["type"] == "spike" else round(random.uniform(40, 120), 1)
    return {
        "status": "degraded" if _fault["active"] else "healthy",
        "service": SERVICE_NAME,
        "memory_percent": round(mem, 2),
        "cpu_percent": round(cpu, 2),
        "error_rate": error_rate,
        "latency_ms": latency_ms,
        "fault": _fault["type"],
        "uptime_seconds": round(time.time() - _start_time, 1),
    }


@app.post("/simulate/leak")
def inject_leak():
    global _leak_thread
    if _fault["active"]:
        return {"ok": False, "msg": "fault already active"}
    _fault["type"] = "leak"
    _fault["active"] = True
    _leak_thread = threading.Thread(target=_run_leak, daemon=True)
    _leak_thread.start()
    return {"ok": True, "fault": "leak", "service": SERVICE_NAME}


@app.post("/simulate/spike")
def inject_spike(duration: int = 120):
    global _spike_until
    _fault["type"] = "spike"
    _fault["active"] = True
    _spike_until = time.time() + duration
    # Auto-reset after duration
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
    return {"ok": True, "service": SERVICE_NAME}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=SERVICE_PORT)
