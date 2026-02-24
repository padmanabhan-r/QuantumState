"""POST /api/pipeline/run — SSE stream through all 3 agents."""
import os
import json
import threading
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

router = APIRouter(tags=["pipeline"])

_SELF_BASE = os.getenv("SELF_BASE_URL", "http://localhost:8000")

# Prevent concurrent pipeline runs — two simultaneous requests both pass the dedup
# check before either writes a REMEDIATING incident, producing duplicate incidents.
_pipeline_lock = threading.Lock()

AGENT_IDS = {
    "cassandra":     "cassandra-detection-agent",
    "archaeologist": "archaeologist-investigation-agent",
    "surgeon":       "surgeon-action-agent",
}

CASSANDRA_PROMPT = """
You are the first agent in the QuantumState incident pipeline.

Scan all services for anomalies. Run your detection tools:
1. detect_memory_leak — find services where memory has peaked above 65% in the last 5 minutes. Use MAX or peak values, not averages — a progressive leak shows as a rising trend.
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
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from orchestrator import converse_stream
    return converse_stream


def _event(name: str, data: dict) -> str:
    return f"event: {name}\ndata: {json.dumps(data)}\n\n"


_ACTION_MAP = {
    "memory_leak_progressive": "rollback_deployment",
    "memory_leak":             "restart_service",
    "error_spike_sudden":      "rollback_deployment",
    "deployment_rollback":     "rollback_deployment",
    "latency_cascade":         "restart_dependency",
    "cache_failure":           "scale_cache",
    "redis_failure":           "restart_dependency",
}

_AUTONOMOUS_MODE = os.getenv("AUTONOMOUS_MODE", "true").lower() == "true"
_CONFIDENCE_THRESHOLD = float(os.getenv("REMEDIATION_CONFIDENCE_THRESHOLD", "0.75"))


def _parse_field_value(text: str, field: str) -> str:
    """Extract a field value from agent output like '- field_name: value'."""
    import re
    for line in text.splitlines():
        clean = re.sub(r"^[\s\-\*]+", "", line).strip()
        m = re.match(rf"^\*{{0,2}}{re.escape(field)}\*{{0,2}}:\s*(.+)", clean, re.IGNORECASE)
        if m:
            return re.sub(r"\*", "", m.group(1)).strip()
    return ""


def _maybe_trigger_remediation(surgeon_output: str, cassandra_output: str,
                                 archaeologist_output: str, incident_id: str = ""):
    """
    Parse Surgeon output. If autonomous mode is on and confidence is sufficient,
    trigger the Kibana Workflow and write the action to ES.
    Yields SSE events for the frontend.
    """
    if not _AUTONOMOUS_MODE:
        return

    service          = _parse_field_value(surgeon_output, "service")
    anomaly_type     = _parse_field_value(surgeon_output, "anomaly_type") or \
                       _parse_field_value(cassandra_output, "anomaly_type")
    root_cause       = _parse_field_value(surgeon_output, "root_cause") or \
                       _parse_field_value(archaeologist_output, "root_cause")
    recommended_action = _parse_field_value(surgeon_output, "recommended_action")
    risk_level       = _parse_field_value(surgeon_output, "risk_level") or "low"

    # Parse confidence score
    confidence_raw = _parse_field_value(surgeon_output, "confidence_score")
    try:
        confidence = float(confidence_raw)
        if confidence > 1.0:        # agent returned 0-100 scale
            confidence = confidence / 100.0
    except (ValueError, TypeError):
        confidence = 0.0

    resolution_status = _parse_field_value(surgeon_output, "resolution_status").upper()

    # If Surgeon successfully triggered the workflow, it returns REMEDIATING.
    # Still emit remediation_triggered so the frontend schedules Guardian,
    # and call /api/workflow/trigger to ensure status=pending is written to ES
    # for the MCP Runner (Kibana Workflow ES-write step may fail silently).
    if resolution_status == "REMEDIATING" and service:
        if not recommended_action:
            recommended_action = _ACTION_MAP.get(anomaly_type.lower(), "restart_service")
        yield _event("remediation_triggered", {
            "agent":      "surgeon",
            "text":       f"Surgeon triggered autonomous remediation: {recommended_action} on {service} "
                          f"(confidence {confidence:.2f}, risk: {risk_level})",
            "service":    service,
            "action":     recommended_action,
            "confidence": confidence,
            "risk_level": risk_level,
        })
        try:
            import requests as _req
            payload = {
                "incident_id":      incident_id,
                "service":          service,
                "action":           recommended_action,
                "anomaly_type":     anomaly_type,
                "root_cause":       root_cause,
                "confidence_score": confidence,
                "risk_level":       risk_level,
            }
            rem_resp = _req.post(
                f"{_SELF_BASE}/api/workflow/trigger",
                json=payload,
                timeout=20,
            )
            rem_data = rem_resp.json() if rem_resp.ok else {}
            yield _event("remediation_executing", {
                "agent":      "surgeon",
                "text":       f"Action written to coordination bus — "
                              f"exec_id: {rem_data.get('exec_id', 'n/a')}",
                "exec_id":    rem_data.get("exec_id", ""),
                "wf_trigger": rem_data.get("workflow_triggered", False),
            })
        except Exception as exc:
            yield _event("remediation_error", {
                "agent": "surgeon",
                "text":  f"Coordination bus write failed: {exc}",
            })
        return

    if not service or confidence < _CONFIDENCE_THRESHOLD:
        if service and confidence > 0:
            yield _event("remediation_skipped", {
                "text": f"Autonomous remediation skipped — confidence {confidence:.2f} below threshold {_CONFIDENCE_THRESHOLD}",
                "agent": "surgeon",
            })
        return

    # Map anomaly type to action if Surgeon didn't provide one
    if not recommended_action:
        recommended_action = _ACTION_MAP.get(anomaly_type.lower(), "restart_service")

    if not incident_id:
        import uuid
        incident_id = str(uuid.uuid4())[:12]

    yield _event("remediation_triggered", {
        "agent": "surgeon",
        "text":  f"Surgeon workflow call failed — fallback trigger: {recommended_action} on {service} "
                 f"(confidence {confidence:.2f}, risk: {risk_level})",
        "service":    service,
        "action":     recommended_action,
        "confidence": confidence,
        "risk_level": risk_level,
    })

    try:
        import requests as _req
        payload = {
            "incident_id":     incident_id,
            "service":         service,
            "action":          recommended_action,
            "anomaly_type":    anomaly_type,
            "root_cause":      root_cause,
            "confidence_score": confidence,
            "risk_level":      risk_level,
        }

        # Write status=pending to remediation-actions-quantumstate so the MCP Runner
        # can pick it up and execute docker restart. Also attempts the Kibana Workflow
        # for Case creation. If Docker is unavailable, MCP Runner calls /api/remediate
        # as its own fallback.
        rem_resp = _req.post(
            f"{_SELF_BASE}/api/workflow/trigger",
            json=payload,
            timeout=20,
        )
        rem_data = rem_resp.json() if rem_resp.ok else {}

        yield _event("remediation_executing", {
            "agent":      "surgeon",
            "text":       f"Action queued for MCP Runner (status=pending) — "
                          f"exec_id: {rem_data.get('exec_id', 'n/a')}",
            "exec_id":    rem_data.get("exec_id", ""),
            "wf_trigger": rem_data.get("workflow_triggered", False),
        })

    except Exception as exc:
        yield _event("remediation_error", {
            "agent": "surgeon",
            "text":  f"Remediation trigger failed: {exc}",
        })


def _pipeline_generator():
    # Prevent concurrent runs — two simultaneous requests both pass the ES dedup
    # check before either writes a REMEDIATING incident, producing duplicate incidents.
    if not _pipeline_lock.acquire(blocking=False):
        yield _event("pipeline_complete", {
            "text": "Pipeline already running — please wait for the current run to complete before triggering another."
        })
        return

    try:
        yield from _pipeline_body()
    finally:
        _pipeline_lock.release()


def _pipeline_body():
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

    from datetime import datetime as _dt2, timezone as _tz2
    pipeline_started_at = _dt2.now(_tz2.utc).isoformat()

    yield _event("agent_start", {"agent": "cassandra", "label": "Cassandra — Detection"})
    full_response = ""
    for evt in converse_stream(AGENT_IDS["cassandra"], CASSANDRA_PROMPT):
        yield _event(evt["event"], {"agent": "cassandra", "text": evt["text"]})
        if evt["event"] == "message_complete":
            full_response = evt["text"]
            cassandra_output = full_response
    yield _event("agent_complete", {"agent": "cassandra", "text": full_response})

    # Stop pipeline if Cassandra found no anomaly or returned nothing
    if not cassandra_output.strip():
        yield _event("pipeline_complete", {"text": "Cassandra returned no output — no data in the detection window or agent error. Pipeline stopped."})
        return
    if "anomaly_detected: false" in cassandra_output.lower():
        yield _event("pipeline_complete", {"text": "No anomaly detected — system is healthy. Pipeline stopped."})
        return

    # Dedup: block only if there is an actively REMEDIATING incident for this service
    # (i.e. the pipeline is mid-flight). RESOLVED / ESCALATE / MONITORING incidents
    # are closed — a new real incident on the same service must not be suppressed.
    # A REMEDIATING incident older than 15 min is considered stale (something went
    # wrong) and is also allowed through.
    from elastic import get_es as _get_es
    from datetime import datetime as _dt, timezone as _tz
    _KNOWN_SERVICES = ["payment-service", "checkout-service", "auth-service", "inventory-service"]
    _detected_services = [s for s in _KNOWN_SERVICES if s in cassandra_output.lower()]
    if _detected_services:
        try:
            _es = _get_es()
            _new_services = []
            _handled_services = []
            for _svc in _detected_services:
                _recent = _es.search(index="incidents-quantumstate*", body={
                    "size": 1,
                    "query": {
                        "bool": {
                            "filter": [
                                {"term": {"service": _svc}},
                                {"term": {"pipeline_run": True}},
                                {"range": {"@timestamp": {"gte": "now-15m"}}},
                            ]
                        }
                    },
                    "sort": [{"@timestamp": "desc"}],
                })
                if _recent["hits"]["total"]["value"] > 0:
                    _last_doc = _recent["hits"]["hits"][0]["_source"]
                    _last_ts  = _last_doc.get("@timestamp", "")
                    _resolution = _last_doc.get("resolution_status", "").upper()
                    try:
                        _age = (_dt.now(_tz.utc) - _dt.fromisoformat(
                            _last_ts.replace("Z", "+00:00")
                        )).total_seconds() / 60
                    except Exception:
                        _age = 0

                    if _resolution == "REMEDIATING" and _age < 15:
                        # Actively in-flight — block
                        _handled_services.append(
                            f"{_svc} (remediating since {_last_ts[:16].replace('T',' ')} UTC)"
                        )
                    elif _resolution == "RESOLVED" and _age < 15:
                        # Cooldown matches the auto-pipeline minimum (15 min).
                        # @timestamp is pipeline start time, not Guardian completion,
                        # so the effective post-resolution window is 15 - pipeline_duration.
                        _handled_services.append(
                            f"{_svc} (resolved {_age:.1f}m ago — cooldown)"
                        )
                    else:
                        # ESCALATE / MONITORING / stale REMEDIATING / RESOLVED > 3 min
                        # — allow new detection
                        _new_services.append(_svc)
                else:
                    _new_services.append(_svc)

            if not _new_services:
                yield _event("pipeline_complete", {
                    "text": f"Skipped — active remediation already in progress: {', '.join(_handled_services)}"
                })
                return
        except Exception:
            pass  # if check fails, continue with pipeline

    arch_prompt = f"""You are the second agent in the QuantumState incident pipeline.

Cassandra reported:

{cassandra_output}

Investigate the root cause. Run: search_error_logs, correlate_deployments, find_similar_incidents.

Return: service, anomaly_type, root_cause, evidence, recommended_action, historical_match, confidence, summary."""

    # Warm up ELSER before Archaeologist runs — Serverless scales to 0 allocations
    # when idle; the first call cold-starts (30-60s) and times out the tool.
    # Sending a dummy inference request here wakes the model so find_similar_incidents
    # hits a warm allocation.
    try:
        from elastic import get_es as _warm_es
        _warm_es().inference.inference(
            inference_id=".elser-2-elasticsearch",
            body={"input": ["warmup"]},
        )
    except Exception:
        pass  # non-fatal — Archaeologist will still run, just may be slower

    yield _event("agent_start", {"agent": "archaeologist", "label": "Archaeologist — Investigation"})
    full_response = ""
    for evt in converse_stream(AGENT_IDS["archaeologist"], arch_prompt):
        yield _event(evt["event"], {"agent": "archaeologist", "text": evt["text"]})
        if evt["event"] == "message_complete":
            full_response = evt["text"]
            archaeologist_output = full_response
    yield _event("agent_complete", {"agent": "archaeologist", "text": full_response})

    import uuid as _uuid
    incident_id = str(_uuid.uuid4())[:12]

    surgeon_prompt = f"""You are the third agent in the QuantumState pipeline.

Incident ID: {incident_id}

Archaeologist findings:
{archaeologist_output}

Cassandra detection:
{cassandra_output}

IMPORTANT: If multiple services were flagged as anomalous, remediate ONLY the single most critical one this run — the service with the highest confidence or most severe metric deviation. Set all other detected services to MONITORING. The pipeline will handle them on the next run.

For the ONE most critical service, run these steps:
1. get_recent_anomaly_metrics — confirm the anomaly is still present for that service
2. log_remediation_action — record the intended action before triggering anything
3. If confidence >= 0.8 and anomaly still present: call quantumstate.autonomous_remediation with ALL of these parameters:
   - incident_id: {incident_id}
   - service: <the service name you are handling>
   - action: <one of: rollback_deployment | restart_service | scale_cache | restart_dependency>
   - anomaly_type: <anomaly type for this service>
   - root_cause: <root cause from Archaeologist for this service>
   - confidence_score: <your confidence as decimal 0.0-1.0>
   - risk_level: <low | medium | high>
4. If confidence < 0.8 or anomaly resolved: do NOT call the workflow — set resolution_status to ESCALATE or MONITORING

Return one output block per detected service using EXACTLY this format (one field per line, dash prefix):
- service: <service name>
- anomaly_type: <type>
- root_cause: <description>
- recommended_action: <one of: rollback_deployment | restart_service | scale_cache | restart_dependency>
- confidence_score: <decimal 0.0 to 1.0, e.g. 0.91>
- risk_level: <one of: low | medium | high>
- resolution_status: REMEDIATING, MONITORING, or ESCALATE
- lessons_learned: <description>
- pipeline_summary: <one sentence>"""

    yield _event("agent_start", {"agent": "surgeon", "label": "Surgeon — Remediation"})
    surgeon_output = ""
    for evt in converse_stream(AGENT_IDS["surgeon"], surgeon_prompt):
        yield _event(evt["event"], {"agent": "surgeon", "text": evt["text"]})
        if evt["event"] == "message_complete":
            surgeon_output = evt["text"]
    yield _event("agent_complete", {"agent": "surgeon", "text": surgeon_output})

    # ── Autonomous remediation trigger ────────────────────────────────────────
    # If confidence is sufficient, trigger the Kibana Workflow + write action to ES
    yield from _maybe_trigger_remediation(
        surgeon_output, cassandra_output, archaeologist_output, incident_id
    )

    # Parse surgeon output and write one incident doc per service found
    try:
        import re
        from datetime import datetime, timezone
        from elastic import get_es

        FIELDS = ("service", "anomaly_type", "root_cause", "action_taken",
                  "recommended_action", "confidence_score", "risk_level",
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
                "@timestamp":         pipeline_started_at,
                "pipeline_run":       True,
                "service":            section.get("service", ""),
                "anomaly_type":       section.get("anomaly_type", ""),
                "root_cause":         section.get("root_cause", ""),
                "action_taken":       section.get("action_taken", ""),
                "recommended_action": section.get("recommended_action", ""),
                "confidence_score":   section.get("confidence_score", ""),
                "risk_level":         section.get("risk_level", ""),
                "resolution_status":  section.get("resolution_status", "MONITORING"),
                "mttr_estimate":      section.get("mttr_estimate", ""),
                "lessons_learned":    section.get("lessons_learned", ""),
                "pipeline_summary":   section.get("pipeline_summary", ""),
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
