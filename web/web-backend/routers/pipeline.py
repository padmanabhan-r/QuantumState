"""POST /api/pipeline/run — SSE stream through all 3 agents."""
import os
import json
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env"))

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

router = APIRouter(tags=["pipeline"])

AGENT_IDS = {
    "cassandra":     "cassandra-detection-agent",
    "archaeologist": "archaeologist-investigation-agent",
    "surgeon":       "surgeon-action-agent",
}

CASSANDRA_PROMPT = """
You are the first agent in the QuantumState incident pipeline.

Scan all services for anomalies. Run your detection tools:
1. detect_memory_leak — find services where memory has peaked above 70% in the last 30 minutes. Use MAX or peak values, not averages — a progressive leak shows as a rising trend.
2. detect_error_spike — find services where error rate > 3 errors/min
3. If an anomaly is found, run calculate_time_to_failure for that service

Return your findings as a structured summary with these exact fields:
- anomaly_detected: true/false
- anomaly_type: (e.g. memory_leak_progressive, error_spike_sudden, deployment_rollback)
- affected_service: (service name)
- affected_region: (e.g. us-east-1)
- current_value: (peak metric reading in last 30 min)
- baseline_value: (24h baseline average)
- deviation_pct: (% above baseline)
- time_to_critical_minutes: (estimated minutes to 90% threshold, or N/A)
- confidence: (0-100)
- summary: (one sentence describing what you found)

If no anomaly is detected, set anomaly_detected to false and stop.
""".strip()


def _get_converse_stream():
    """Import converse_stream from ingest/orchestrator.py."""
    try:
        from ingest.orchestrator import converse_stream
        return converse_stream
    except ImportError:
        # Try direct path
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "orchestrator",
            os.path.join(os.path.dirname(__file__), "..", "..", "..", "ingest", "orchestrator.py"),
        )
        mod = importlib.util.load_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.converse_stream


def _event(name: str, data: dict) -> str:
    return f"event: {name}\ndata: {json.dumps(data)}\n\n"


def _pipeline_generator():
    try:
        converse_stream = _get_converse_stream()
    except Exception as exc:
        yield _event("error", {"text": f"Could not load orchestrator: {exc}"})
        return

    agents = [
        ("cassandra",     "Cassandra",     CASSANDRA_PROMPT),
    ]

    cassandra_output = ""
    archaeologist_output = ""

    yield _event("agent_start", {"agent": "cassandra", "label": "Cassandra — Detection"})
    full_response = ""
    for evt in converse_stream(AGENT_IDS["cassandra"], CASSANDRA_PROMPT):
        yield _event(evt["event"], {"agent": "cassandra", "text": evt["text"]})
        if evt["event"] == "message_complete":
            full_response = evt["text"]
            cassandra_output = full_response
    yield _event("agent_complete", {"agent": "cassandra", "text": full_response})

    # Stop pipeline if Cassandra found no anomaly
    if "anomaly_detected: false" in cassandra_output.lower():
        yield _event("pipeline_complete", {"text": "No anomaly detected — system is healthy. Pipeline stopped."})
        return

    arch_prompt = f"""You are the second agent in the QuantumState incident pipeline.

Cassandra reported:

{cassandra_output}

Investigate the root cause. Run: search_error_logs, correlate_deployments, find_similar_incidents.

Return: service, anomaly_type, root_cause, evidence, recommended_action, historical_match, confidence, summary."""

    yield _event("agent_start", {"agent": "archaeologist", "label": "Archaeologist — Investigation"})
    full_response = ""
    for evt in converse_stream(AGENT_IDS["archaeologist"], arch_prompt):
        yield _event(evt["event"], {"agent": "archaeologist", "text": evt["text"]})
        if evt["event"] == "message_complete":
            full_response = evt["text"]
            archaeologist_output = full_response
    yield _event("agent_complete", {"agent": "archaeologist", "text": full_response})

    surgeon_prompt = f"""You are the third agent in the QuantumState pipeline.

Archaeologist findings:
{archaeologist_output}

Cassandra detection:
{cassandra_output}

Run: get_recent_anomaly_metrics, verify_resolution, log_remediation_action.

Return the final incident report using EXACTLY this format (one field per line, dash prefix):
- service: <service name>
- anomaly_type: <type>
- root_cause: <description>
- action_taken: <what was done>
- resolution_status: RESOLVED, PARTIALLY_RESOLVED, MONITORING, or ESCALATE
- mttr_estimate: <e.g. 4 min>
- lessons_learned: <description>
- pipeline_summary: <one sentence>"""

    yield _event("agent_start", {"agent": "surgeon", "label": "Surgeon — Remediation"})
    surgeon_output = ""
    for evt in converse_stream(AGENT_IDS["surgeon"], surgeon_prompt):
        yield _event(evt["event"], {"agent": "surgeon", "text": evt["text"]})
        if evt["event"] == "message_complete":
            surgeon_output = evt["text"]
    yield _event("agent_complete", {"agent": "surgeon", "text": surgeon_output})

    # Parse surgeon output and write one incident doc per service found
    try:
        import re
        from datetime import datetime, timezone
        from elastic import get_es

        FIELDS = ("service", "anomaly_type", "root_cause", "action_taken",
                  "resolution_status", "mttr_estimate", "lessons_learned",
                  "pipeline_summary")

        def parse_field(line: str):
            """Extract (field, value) from a line regardless of markdown formatting.
            Handles: '- service: x', '- **service:** x', '**Service:** x', 'service: x'
            """
            # Strip leading whitespace, dashes, asterisks
            clean = re.sub(r"^[\s\-\*]+", "", line).strip()
            for f in FIELDS:
                # field name may be wrapped in ** or not, colon follows
                m = re.match(rf"^\*{{0,2}}{re.escape(f)}\*{{0,2}}:\s*(.+)", clean, re.IGNORECASE)
                if m:
                    return f, re.sub(r"\*", "", m.group(1)).strip()
            return None, None

        # Split surgeon output into per-service sections by finding each "service:" line
        sections = []
        current: dict = {}
        for line in surgeon_output.splitlines():
            field, value = parse_field(line)
            if field == "service":
                if current.get("service"):   # save previous section
                    sections.append(current)
                current = {"service": value}
            elif field and current:
                current[field] = value
        if current.get("service"):
            sections.append(current)

        # Fallback: single section with whatever was parsed
        if not sections:
            merged: dict = {}
            for line in surgeon_output.splitlines():
                field, value = parse_field(line)
                if field and field not in merged:
                    merged[field] = value
            if merged:
                sections = [merged]

        es = get_es()
        written_ids = []
        for section in sections:
            doc = {
                "@timestamp":        datetime.now(timezone.utc).isoformat(),
                "pipeline_run":      True,
                "service":           section.get("service", ""),
                "anomaly_type":      section.get("anomaly_type", ""),
                "root_cause":        section.get("root_cause", ""),
                "action_taken":      section.get("action_taken", ""),
                "resolution_status": section.get("resolution_status", "MONITORING"),
                "mttr_estimate":     section.get("mttr_estimate", ""),
                "lessons_learned":   section.get("lessons_learned", ""),
                "pipeline_summary":  section.get("pipeline_summary", ""),
            }
            result = es.index(index="incidents-quantumstate", document=doc)
            written_ids.append(result["_id"])

        yield _event("pipeline_complete", {
            "text": f"Pipeline complete — {len(written_ids)} incident(s) written to Elasticsearch"
        })
    except Exception as exc:
        yield _event("pipeline_complete", {"text": f"Pipeline finished. (Write failed: {exc})"})


@router.post("/pipeline/run")
def run_pipeline():
    return StreamingResponse(
        _pipeline_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
