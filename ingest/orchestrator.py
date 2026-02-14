"""
QuantumState — Agent Orchestrator

Chains Cassandra → Archaeologist → Surgeon via the Agent Builder /converse API.
Each agent's output is injected into the next agent's prompt.
The final incident report is written to incidents-quantumstate.
"""

import os
import json
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv
from elasticsearch import Elasticsearch

load_dotenv()

API_KEY     = os.getenv("ELASTIC_API_KEY", "")
ELASTIC_URL = os.getenv("ELASTIC_URL", "").rstrip("/")


def _derive_kibana_url() -> str:
    explicit = os.getenv("KIBANA_URL", "").strip().rstrip("/")
    if explicit:
        return explicit
    cloud_id = os.getenv("ELASTIC_CLOUD_ID", "")
    if not cloud_id:
        return ""
    try:
        import base64
        _, encoded = cloud_id.split(":", 1)
        decoded = base64.b64decode(encoded + "==").decode("utf-8")
        parts = decoded.rstrip("\x00").split("$")
        if len(parts) >= 3:
            return f"https://{parts[2]}.{parts[0]}"
        elif len(parts) == 2:
            return f"https://{parts[1]}.{parts[0]}"
    except Exception:
        pass
    return ""


KIBANA_URL = _derive_kibana_url()

AGENT_IDS = {
    "cassandra":     "cassandra-detection-agent",
    "archaeologist": "archaeologist-investigation-agent",
    "surgeon":       "surgeon-action-agent",
}

CASSANDRA_PROMPT = """
You are the first agent in the QuantumState incident pipeline.

Scan all services right now for anomalies. Run your detection tools:
1. detect_memory_leak — find services where memory deviation > 20% above baseline
2. detect_error_spike — find services where error rate > 3 errors/min
3. If an anomaly is found, run calculate_time_to_failure for that service

Return your findings as a structured summary with these exact fields:
- anomaly_detected: true/false
- anomaly_type: (e.g. memory_leak_progressive, error_spike_sudden, deployment_rollback)
- affected_service: (service name)
- affected_region: (e.g. us-east-1)
- current_value: (current metric reading)
- baseline_value: (24h baseline)
- deviation_pct: (% above baseline)
- time_to_critical_minutes: (estimated minutes to 90% threshold, or N/A)
- confidence: (0–100)
- summary: (one sentence describing what you found)

If no anomaly is detected, set anomaly_detected to false and stop.
""".strip()

ARCHAEOLOGIST_PROMPT = """
You are the second agent in the QuantumState incident pipeline.

Cassandra (the detection agent) has reported the following anomaly:

{cassandra_output}

Investigate the root cause. Run your investigation tools:
1. search_error_logs — search for ERROR/CRITICAL logs for the affected service
2. correlate_deployments — check for deploy events in the last 2 hours
3. find_similar_incidents — find historical incidents with the same anomaly type

Return your findings with these exact fields:
- service: (service name)
- anomaly_type: (pass through from Cassandra)
- root_cause: (your determination of what caused this)
- evidence: (key evidence — log patterns, deploy events, historical matches)
- recommended_action: (specific remediation action)
- historical_match: (similar past incident if found, or "none")
- confidence: (0–100)
- summary: (two sentences: what happened and why)
""".strip()

SURGEON_PROMPT = """
You are the third and final agent in the QuantumState incident pipeline.

The Archaeologist has identified the root cause:

{archaeologist_output}

Original detection by Cassandra:
{cassandra_output}

Your job:
1. Run get_recent_anomaly_metrics for the affected service to see current state
2. Run verify_resolution to check if memory, error rate, latency are within healthy thresholds
3. Run log_remediation_action to record the action in the audit trail

Return a final incident report with these exact fields:
- service: (service name)
- anomaly_type: (from Cassandra)
- root_cause: (from Archaeologist)
- action_taken: (what remediation was executed)
- resolution_status: RESOLVED, MONITORING, or ESCALATE
- current_memory_pct: (latest reading)
- current_error_rate: (latest reading)
- current_latency_ms: (latest reading)
- mttr_estimate: (e.g. "~4 minutes")
- lessons_learned: (one sentence for post-mortem)
- pipeline_summary: (three sentences covering detection → investigation → resolution)
""".strip()


# ── SSE event types emitted by /converse/async ────────────────────────────────
# conversation_id_set  — first event, gives conversation ID
# reasoning            — agent thinking step (transient label)
# thinking_complete    — reasoning phase done, time_to_first_token
# message_chunk        — one token / small chunk of the final response
# message_complete     — full assembled response text

def converse_stream(agent_id: str, message: str):
    """
    Call /api/agent_builder/converse/async and yield parsed SSE events as dicts:
        {"event": "reasoning",       "text": "Consulting my tools"}
        {"event": "message_chunk",   "text": "payment"}
        {"event": "message_complete","text": "<full response>"}
        {"event": "error",           "text": "<error message>"}
    """
    url = f"{KIBANA_URL}/api/agent_builder/converse/async"
    headers = {
        "Authorization": f"ApiKey {API_KEY}",
        "kbn-xsrf":      "true",
        "Content-Type":  "application/json",
        "Accept":        "text/event-stream",
    }
    payload = {"agent_id": agent_id, "input": message}

    try:
        resp = requests.post(url, headers=headers, json=payload,
                             timeout=180, stream=True)
        resp.raise_for_status()
    except Exception as exc:
        yield {"event": "error", "text": str(exc)}
        return

    current_event = None
    for raw_line in resp.iter_lines():
        if not raw_line:
            current_event = None
            continue

        # iter_lines returns bytes
        line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line

        # SSE keepalive padding lines — skip
        if line.startswith(":"):
            continue

        if line.startswith("event:"):
            current_event = line[len("event:"):].strip()
            continue

        if line.startswith("data:"):
            raw_data = line[len("data:"):].strip()
            try:
                data = json.loads(raw_data).get("data", {})
            except json.JSONDecodeError:
                continue

            if current_event == "reasoning":
                text = data.get("reasoning", "")
                if text:
                    yield {"event": "reasoning", "text": text}

            elif current_event == "message_chunk":
                chunk = data.get("text_chunk", "")
                if chunk:
                    yield {"event": "message_chunk", "text": chunk}

            elif current_event == "message_complete":
                full = data.get("message_content", "")
                yield {"event": "message_complete", "text": full}

            elif current_event == "thinking_complete":
                ttft = data.get("time_to_first_token", 0)
                yield {"event": "thinking_complete",
                       "text": f"Thinking complete ({ttft}ms)"}


def _write_incident(es: Elasticsearch, report: dict) -> str:
    """Write the resolved incident to incidents-quantumstate. Returns doc ID."""
    doc = {
        "@timestamp":           datetime.now(timezone.utc).isoformat(),
        "pipeline_run":         True,
        "service":              report.get("service", "unknown"),
        "anomaly_type":         report.get("anomaly_type", "unknown"),
        "root_cause":           report.get("root_cause", ""),
        "action_taken":         report.get("action_taken", ""),
        "resolution_status":    report.get("resolution_status", "UNKNOWN"),
        "mttr_estimate":        report.get("mttr_estimate", ""),
        "lessons_learned":      report.get("lessons_learned", ""),
        "pipeline_summary":     report.get("pipeline_summary", ""),
        "cassandra_output":     report.get("cassandra_raw", ""),
        "archaeologist_output": report.get("archaeologist_raw", ""),
        "surgeon_output":       report.get("surgeon_raw", ""),
    }
    result = es.index(index="incidents-quantumstate", document=doc)
    return result["_id"]


def _get_es() -> Elasticsearch:
    cloud_id = os.getenv("ELASTIC_CLOUD_ID")
    if cloud_id:
        return Elasticsearch(cloud_id=cloud_id, api_key=API_KEY, request_timeout=15)
    return Elasticsearch(ELASTIC_URL, api_key=API_KEY, request_timeout=15)
