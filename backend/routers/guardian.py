"""
Guardian — Self-Healing Verification Loop

A Kibana Agent Builder agent that verifies remediation success.
The background worker schedules calls to the Guardian agent 60s after
a remediation action executes, streams its reasoning, and updates incidents.

Routes:
  GET  /api/guardian/status          — worker state + recent verdicts
  POST /api/guardian/stream/{service} — SSE: run Guardian agent live for a service
"""

import os
import sys
import json
import threading
import logging
from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

logger = logging.getLogger("guardian")
router = APIRouter(tags=["guardian"])

GUARDIAN_AGENT_ID = "guardian-verification-agent"

# ---------------------------------------------------------------------------
# Guardian Agent Prompt
# Paste this into Kibana Agent Builder when creating the Guardian agent.
# Attach tools: get_recent_anomaly_metrics, verify_resolution
# Optionally attach the QuantumState remediation workflow as a tool.
# ---------------------------------------------------------------------------
GUARDIAN_PROMPT_TEMPLATE = """
You are the fourth and final agent in the QuantumState incident pipeline — the Guardian.

Your role: Verify that the autonomous remediation was successful and close the incident loop.

A remediation action has just been executed:
- Service:   {service}
- Action:    {action}
- Anomaly:   {anomaly_type}
- Root cause: {root_cause}
- Executed:  {executed_at}
- Exec ID:   {exec_id}

Run your verification tools:
1. get_recent_anomaly_metrics — get the current metrics for {service}
2. verify_resolution — check if memory, error rate, and latency are within healthy thresholds

Recovery thresholds (all must pass for RESOLVED):
- memory_percent < 65%
- error_rate < 2 errors/min
- request_latency_ms < 250ms

Return your verdict using EXACTLY this format (one field per line, dash prefix):
- service: {service}
- verdict: RESOLVED or ESCALATE
- memory_pct: <current average reading>
- error_rate: <current average reading>
- latency_ms: <current average reading>
- mttr_estimate: <e.g. ~4m 12s>
- confidence: <0-100>
- summary: <one sentence: what you verified and the outcome>
""".strip()

# ---------------------------------------------------------------------------
# Worker state
# ---------------------------------------------------------------------------
_worker_state = {
    "running":         False,
    "last_check_at":   None,
    "checks_run":      0,
    "resolved_count":  0,
    "escalated_count": 0,
    "recent_verdicts": [],
}
_checked_exec_ids: set = set()
_state_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_es():
    from elastic import get_es
    return get_es()


def _fmt_mttr(seconds: int) -> str:
    if seconds < 60:
        return f"~{seconds}s"
    mins = seconds // 60
    secs = seconds % 60
    return f"~{mins}m {secs}s" if secs else f"~{mins}m"


def _find_incident(es, service: str, since_minutes: int = 60) -> dict | None:
    result = es.search(
        index="incidents-quantumstate*",
        body={
            "size": 1,
            "query": {
                "bool": {
                    "filter": [
                        {"term":  {"service": service}},
                        {"term":  {"pipeline_run": True}},
                        {"range": {"@timestamp": {"gte": f"now-{since_minutes}m"}}},
                    ]
                }
            },
            "sort": [{"@timestamp": "desc"}],
        }
    )
    hits = result["hits"]["hits"]
    return hits[0] if hits else None


def _update_incident(es, incident_hit: dict, verdict: str, mttr_seconds: int,
                     guardian_output: str, mttr_display: str = "") -> None:
    status = "RESOLVED" if verdict == "RESOLVED" else "ESCALATE"
    patch = {
        "resolution_status": status,
        "guardian_verified": True,
        "guardian_output":   guardian_output,
        "mttr_seconds":      mttr_seconds,
        "mttr_estimate":     mttr_display or _fmt_mttr(mttr_seconds),
    }
    if status == "RESOLVED":
        patch["resolved_at"] = datetime.now(timezone.utc).isoformat()
    else:
        patch["escalated_at"] = datetime.now(timezone.utc).isoformat()

    es.update(
        index=incident_hit["_index"],
        id=incident_hit["_id"],
        body={"doc": patch},
    )


def _parse_field(text: str, field: str) -> str:
    import re
    for line in text.splitlines():
        clean = re.sub(r"^[\s\-\*]+", "", line).strip()
        m = re.match(rf"^\*{{0,2}}{re.escape(field)}\*{{0,2}}:\s*(.+)", clean, re.IGNORECASE)
        if m:
            return re.sub(r"\*", "", m.group(1)).strip()
    return ""


def _event(name: str, data: dict) -> str:
    return f"event: {name}\ndata: {json.dumps(data)}\n\n"


# ---------------------------------------------------------------------------
# Core: run Guardian agent via Agent Builder
# ---------------------------------------------------------------------------

def _run_guardian_agent(action: dict) -> dict:
    """
    Call the Guardian Kibana Agent Builder agent with the remediation context.
    Collects the full response, parses RESOLVED/ESCALATE, updates the incident.
    Returns a verdict dict.
    """
    from orchestrator import converse_stream

    service     = action.get("service", "")
    exec_id     = action.get("exec_id", "")
    executed_at = action.get("executed_at") or action.get("@timestamp", "")

    # Build the prompt
    prompt = GUARDIAN_PROMPT_TEMPLATE.format(
        service     = service,
        action      = action.get("action", ""),
        anomaly_type= action.get("anomaly_type", ""),
        root_cause  = action.get("root_cause", ""),
        executed_at = executed_at,
        exec_id     = exec_id,
    )

    # Call Agent Builder
    full_output = ""
    for evt in converse_stream(GUARDIAN_AGENT_ID, prompt):
        if evt["event"] == "message_complete":
            full_output = evt["text"]

    if not full_output:
        raise RuntimeError("Guardian agent returned no output")

    # Parse verdict from agent response
    verdict      = _parse_field(full_output, "verdict").upper()
    mttr_raw     = _parse_field(full_output, "mttr_estimate")
    confidence   = _parse_field(full_output, "confidence")
    summary      = _parse_field(full_output, "summary")
    memory_pct   = _parse_field(full_output, "memory_pct")
    error_rate   = _parse_field(full_output, "error_rate")
    latency_ms   = _parse_field(full_output, "latency_ms")

    if verdict not in ("RESOLVED", "ESCALATE"):
        # fallback: check for keywords in the output
        verdict = "RESOLVED" if "resolved" in full_output.lower() else "ESCALATE"

    # Calculate MTTR from incident timestamp
    es = _get_es()
    incident_hit = _find_incident(es, service)
    mttr_seconds = 0
    if incident_hit:
        try:
            inc_ts = datetime.fromisoformat(
                incident_hit["_source"]["@timestamp"].replace("Z", "+00:00")
            )
            mttr_seconds = int((datetime.now(timezone.utc) - inc_ts).total_seconds())
        except Exception:
            pass
        _update_incident(es, incident_hit, verdict, mttr_seconds, full_output, mttr_raw)
        es.indices.refresh(index="incidents-quantumstate")

    # Audit trail
    es.index(
        index="agent-decisions-quantumstate",
        document={
            "@timestamp":  datetime.now(timezone.utc).isoformat(),
            "agent":       "guardian",
            "service":     service,
            "exec_id":     exec_id,
            "decision":    verdict,
            "mttr_seconds":mttr_seconds,
            "summary":     summary,
            "raw_output":  full_output,
        }
    )

    return {
        "service":      service,
        "exec_id":      exec_id,
        "verdict":      verdict,
        "mttr_seconds": mttr_seconds,
        "mttr_fmt":     mttr_raw or _fmt_mttr(mttr_seconds),
        "confidence":   confidence,
        "summary":      summary,
        "memory_pct":   memory_pct,
        "error_rate":   error_rate,
        "latency_ms":   latency_ms,
        "checked_at":   datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Background worker
# ---------------------------------------------------------------------------

def _do_scan() -> None:
    es = _get_es()
    result = es.search(
        index="remediation-actions-quantumstate*",
        body={
            "size": 10,
            "query": {
                "bool": {
                    "filter": [
                        {"term":  {"status": "executed"}},
                        {"range": {"executed_at": {
                            "gte": "now-10m",
                            "lte": "now-60s",
                        }}},
                    ]
                }
            },
            "sort": [{"executed_at": "asc"}],
        }
    )

    actions = [h["_source"] for h in result["hits"]["hits"]]

    with _state_lock:
        _worker_state["last_check_at"] = datetime.now(timezone.utc).isoformat()
        _worker_state["checks_run"] += 1

    for action in actions:
        exec_id = action.get("exec_id", "")
        if exec_id in _checked_exec_ids:
            continue
        _checked_exec_ids.add(exec_id)

        try:
            verdict = _run_guardian_agent(action)
            logger.info(
                f"Guardian: {verdict['verdict']} | {verdict['service']} | {verdict['mttr_fmt']}"
            )
            with _state_lock:
                if verdict["verdict"] == "RESOLVED":
                    _worker_state["resolved_count"] += 1
                else:
                    _worker_state["escalated_count"] += 1
                _worker_state["recent_verdicts"] = (
                    [verdict] + _worker_state["recent_verdicts"]
                )[:10]

        except Exception as exc:
            logger.warning(f"Guardian agent call failed exec_id={exec_id}: {exc}")


def _guardian_loop(stop_event: threading.Event) -> None:
    with _state_lock:
        _worker_state["running"] = True
    logger.info("Guardian worker started")

    while not stop_event.is_set():
        try:
            _do_scan()
        except Exception as exc:
            logger.warning(f"Guardian scan error: {exc}")
        stop_event.wait(timeout=30)

    with _state_lock:
        _worker_state["running"] = False
    logger.info("Guardian worker stopped")


_stop_event: threading.Event | None = None
_worker_thread: threading.Thread | None = None


def start_guardian():
    global _stop_event, _worker_thread
    if _worker_thread and _worker_thread.is_alive():
        return
    _stop_event = threading.Event()
    _worker_thread = threading.Thread(
        target=_guardian_loop,
        args=(_stop_event,),
        daemon=True,
        name="guardian-worker",
    )
    _worker_thread.start()


def stop_guardian():
    if _stop_event:
        _stop_event.set()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/guardian/status")
def guardian_status():
    with _state_lock:
        return dict(_worker_state)


@router.post("/guardian/stream/{service}")
def stream_guardian(service: str):
    """
    SSE endpoint — runs the Guardian Kibana agent live for a service.
    The frontend calls this after remediation fires to stream Guardian's
    reasoning directly into the console terminal.
    """
    def generator():
        from orchestrator import converse_stream

        # Find the most recent action for context
        try:
            es = _get_es()
            result = es.search(
                index="remediation-actions-quantumstate*",
                body={
                    "size": 1,
                    "query": {
                        "bool": {
                            "filter": [
                                {"term": {"service": service}},
                                {"range": {"@timestamp": {"gte": "now-30m"}}},
                            ]
                        }
                    },
                    "sort": [{"@timestamp": "desc"}],
                }
            )
            hits = result["hits"]["hits"]
            action = hits[0]["_source"] if hits else {}
        except Exception:
            action = {}

        prompt = GUARDIAN_PROMPT_TEMPLATE.format(
            service     = service,
            action      = action.get("action", "unknown"),
            anomaly_type= action.get("anomaly_type", "unknown"),
            root_cause  = action.get("root_cause", "See incident record"),
            executed_at = action.get("executed_at", "recently"),
            exec_id     = action.get("exec_id", ""),
        )

        yield _event("agent_start", {
            "agent": "guardian",
            "label": "Guardian — Verification",
        })

        full_output = ""
        try:
            for evt in converse_stream(GUARDIAN_AGENT_ID, prompt):
                yield _event(evt["event"], {"agent": "guardian", "text": evt["text"]})
                if evt["event"] == "message_complete":
                    full_output = evt["text"]
        except Exception as exc:
            yield _event("error", {"agent": "guardian", "text": str(exc)})
            return

        yield _event("agent_complete", {"agent": "guardian", "text": full_output})

        # Parse + update incident
        verdict = _parse_field(full_output, "verdict").upper()
        if verdict not in ("RESOLVED", "ESCALATE"):
            verdict = "RESOLVED" if "resolved" in full_output.lower() else "ESCALATE"

        mttr_raw = _parse_field(full_output, "mttr_estimate")
        summary  = _parse_field(full_output, "summary")

        try:
            es = _get_es()
            incident_hit = _find_incident(es, service)
            mttr_seconds = 0
            if incident_hit:
                try:
                    inc_ts = datetime.fromisoformat(
                        incident_hit["_source"]["@timestamp"].replace("Z", "+00:00")
                    )
                    mttr_seconds = int((datetime.now(timezone.utc) - inc_ts).total_seconds())
                except Exception:
                    pass
                _update_incident(es, incident_hit, verdict, mttr_seconds, full_output, mttr_raw)
                es.indices.refresh(index="incidents-quantumstate")

            exec_id = action.get("exec_id", "")
            if exec_id:
                _checked_exec_ids.add(exec_id)

            with _state_lock:
                if verdict == "RESOLVED":
                    _worker_state["resolved_count"] += 1
                else:
                    _worker_state["escalated_count"] += 1

            yield _event("guardian_verdict", {
                "agent":        "guardian",
                "text":         f"Verdict: {verdict} | MTTR: {mttr_raw or _fmt_mttr(mttr_seconds)} | {summary}",
                "verdict":      verdict,
                "mttr_fmt":     mttr_raw or _fmt_mttr(mttr_seconds),
                "mttr_seconds": mttr_seconds,
                "summary":      summary,
            })

        except Exception as exc:
            yield _event("error", {"agent": "guardian", "text": f"Incident update failed: {exc}"})

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
