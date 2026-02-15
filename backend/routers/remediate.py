"""
POST /api/remediate        — Execute metric recovery for a service
GET  /api/actions          — List recent remediation actions
POST /api/workflow/trigger — Trigger the Kibana remediation workflow
"""

import os
import json
import uuid
import requests
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

router = APIRouter(tags=["remediate"])

# ---------------------------------------------------------------------------
# Recovery profiles — how each action type restores metrics over time
# ---------------------------------------------------------------------------
_RECOVERY_PROFILES = {
    "rollback_deployment": {
        "memory_pct":  [88, 82, 74, 66, 58, 52, 48, 45],  # progressive drop
        "error_rate":  [18, 12,  6,  2,  1, 0.4, 0.3, 0.2],
        "latency_ms":  [980, 820, 650, 480, 320, 220, 165, 150],
        "cpu_pct":     [82, 76, 68, 60, 54, 50, 48, 47],
    },
    "restart_service": {
        "memory_pct":  [85, 78, 65, 55, 50, 47, 45, 44],
        "error_rate":  [22, 15,  4,  1, 0.5, 0.3, 0.2, 0.2],
        "latency_ms":  [950, 700, 450, 280, 200, 165, 152, 148],
        "cpu_pct":     [79, 70, 62, 55, 50, 48, 47, 46],
    },
    "scale_cache": {
        "memory_pct":  [72, 68, 64, 60, 57, 55, 53, 52],
        "error_rate":  [5,  3.5, 2, 1.2, 0.8, 0.5, 0.3, 0.2],
        "latency_ms":  [1100, 850, 600, 380, 250, 190, 162, 150],
        "cpu_pct":     [75, 70, 65, 60, 56, 53, 51, 49],
    },
    "restart_dependency": {
        "memory_pct":  [70, 65, 60, 56, 53, 51, 50, 49],
        "error_rate":  [28, 18, 8,  3,  1, 0.5, 0.3, 0.2],
        "latency_ms":  [1200, 900, 650, 400, 250, 180, 155, 148],
        "cpu_pct":     [80, 72, 64, 57, 52, 50, 48, 47],
    },
}

_DEFAULT_PROFILE = _RECOVERY_PROFILES["restart_service"]

_SERVICE_REGIONS = {
    "payment-service":   "us-east-1",
    "checkout-service":  "us-east-1",
    "auth-service":      "us-west-2",
    "inventory-service": "us-east-1",
}


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


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class RemediateRequest(BaseModel):
    incident_id: str
    service: str
    action: str
    confidence_score: float = 0.9
    anomaly_type: str = ""
    root_cause: str = ""
    risk_level: str = "low"


class WorkflowTriggerRequest(BaseModel):
    incident_id: str
    service: str
    action: str
    anomaly_type: str
    root_cause: str
    confidence_score: float
    risk_level: str = "low"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_es():
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from elastic import get_es
    return get_es()


def _write_recovery_metrics(service: str, action: str) -> int:
    """Write 8 recovery data points spread over 8 minutes into ES."""
    es = _get_es()
    profile = _RECOVERY_PROFILES.get(action, _DEFAULT_PROFILE)
    region = _SERVICE_REGIONS.get(service, "us-east-1")
    now = datetime.now(timezone.utc)
    docs = []

    for i, (mem, err, lat, cpu) in enumerate(zip(
        profile["memory_pct"],
        profile["error_rate"],
        profile["latency_ms"],
        profile["cpu_pct"],
    )):
        ts = now + timedelta(seconds=i * 60)  # 1 data point per minute
        base = {
            "@timestamp": ts.isoformat(),
            "service": service,
            "region": region,
            "unit": "percent",
        }
        docs.extend([
            {**base, "metric_type": "memory_percent",      "value": float(mem)},
            {**base, "metric_type": "cpu_percent",         "value": float(cpu)},
            {**base, "metric_type": "error_rate",          "value": float(err),    "unit": "errors/min"},
            {**base, "metric_type": "request_latency_ms",  "value": float(lat),    "unit": "ms"},
        ])

    if not docs:
        return 0

    from elasticsearch.helpers import bulk
    actions = [{"_index": "metrics-quantumstate", "_source": doc} for doc in docs]
    ok, _ = bulk(es, actions)
    es.indices.refresh(index="metrics-quantumstate")
    return ok


def _write_remediation_result(incident_id: str, service: str, action: str,
                               exec_id: str, outcome: str = "success") -> None:
    """Write result to remediation-results-quantumstate."""
    es = _get_es()
    es.index(
        index="remediation-results-quantumstate",
        document={
            "@timestamp": datetime.now(timezone.utc).isoformat(),
            "incident_id": incident_id,
            "service": service,
            "action": action,
            "exec_id": exec_id,
            "outcome": outcome,
            "recovery_initiated": True,
        },
    )
    es.indices.refresh(index="remediation-results-quantumstate")


def _write_action_to_es(req: RemediateRequest, exec_id: str, status: str) -> None:
    """Write or update the action record in remediation-actions-quantumstate."""
    es = _get_es()
    es.index(
        index="remediation-actions-quantumstate",
        document={
            "@timestamp": datetime.now(timezone.utc).isoformat(),
            "incident_id": req.incident_id,
            "service": req.service,
            "action": req.action,
            "anomaly_type": req.anomaly_type,
            "confidence_score": req.confidence_score,
            "risk_level": req.risk_level,
            "triggered_by": "surgeon-agent",
            "status": status,
            "exec_id": exec_id,
            "executed_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    es.indices.refresh(index="remediation-actions-quantumstate")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/remediate")
def execute_remediation(req: RemediateRequest):
    """
    Execute metric recovery for the given service and action.
    Writes recovery data points to metrics-quantumstate so Cassandra
    will detect resolution on the next pipeline run.
    """
    exec_id = str(uuid.uuid4())[:8]

    try:
        # Write recovery metrics to ES
        points_written = _write_recovery_metrics(req.service, req.action)

        # Record the action execution
        _write_action_to_es(req, exec_id, "executed")
        _write_remediation_result(req.incident_id, req.service, req.action, exec_id, "success")

        return {
            "exec_id": exec_id,
            "status": "executed",
            "service": req.service,
            "action": req.action,
            "recovery_points_written": points_written,
            "estimated_recovery_minutes": 4,
            "message": f"Recovery initiated for {req.service}. "
                       f"Metrics will normalise over ~4 minutes. "
                       f"Next pipeline run will detect resolution.",
        }
    except Exception as exc:
        _write_action_to_es(req, exec_id, "failed")
        return {
            "exec_id": exec_id,
            "status": "failed",
            "error": str(exc),
        }


@router.get("/actions")
def list_actions(limit: int = 20):
    """List recent remediation actions from remediation-actions-quantumstate."""
    try:
        es = _get_es()
        result = es.search(
            index="remediation-actions-quantumstate*",
            body={
                "size": limit,
                "sort": [{"@timestamp": "desc"}],
                "_source": [
                    "@timestamp", "incident_id", "service", "action",
                    "anomaly_type", "confidence_score", "risk_level",
                    "status", "exec_id", "triggered_by", "executed_at",
                ],
                "query": {"match_all": {}},
            },
        )
        hits = result["hits"]["hits"]
        return {"actions": [h["_source"] for h in hits], "total": len(hits)}
    except Exception as exc:
        return {"actions": [], "error": str(exc)}


@router.post("/workflow/trigger")
def trigger_kibana_workflow(req: WorkflowTriggerRequest):
    """
    Trigger the Kibana remediation workflow via API.
    Falls back to direct ES write if workflow endpoint is unavailable.
    """
    kibana_url = _derive_kibana_url()
    api_key = os.getenv("ELASTIC_API_KEY", "")
    workflow_id = os.getenv("REMEDIATION_WORKFLOW_ID", "")

    workflow_triggered = False
    workflow_error = None

    # Attempt to trigger Kibana Workflow if ID is configured
    if workflow_id and kibana_url and api_key:
        try:
            url = f"{kibana_url}/api/workflows/{workflow_id}/run"
            headers = {
                "Authorization": f"ApiKey {api_key}",
                "kbn-xsrf": "true",
                "x-elastic-internal-origin": "Kibana",
                "Content-Type": "application/json",
            }
            payload = {
                "inputs": {
                    "incident_id":     req.incident_id,
                    "service":         req.service,
                    "action":          req.action,
                    "anomaly_type":    req.anomaly_type,
                    "root_cause":      req.root_cause,
                    "confidence_score": req.confidence_score,
                    "risk_level":      req.risk_level,
                }
            }
            resp = requests.post(url, headers=headers, json=payload, timeout=15)
            if resp.ok:
                workflow_triggered = True
            else:
                workflow_error = f"{resp.status_code}: {resp.text[:200]}"
        except Exception as exc:
            workflow_error = str(exc)

    # Always write directly to ES as the coordination bus
    # (runner polls this regardless of whether Kibana Workflow fired)
    exec_id = str(uuid.uuid4())[:8]
    try:
        es = _get_es()
        es.index(
            index="remediation-actions-quantumstate",
            document={
                "@timestamp":      datetime.now(timezone.utc).isoformat(),
                "incident_id":     req.incident_id,
                "service":         req.service,
                "action":          req.action,
                "anomaly_type":    req.anomaly_type,
                "root_cause":      req.root_cause,
                "confidence_score": req.confidence_score,
                "risk_level":      req.risk_level,
                "triggered_by":    "surgeon-agent",
                "status":          "pending",
                "workflow_triggered": workflow_triggered,
                "exec_id":         exec_id,
            },
        )
        es.indices.refresh(index="remediation-actions-quantumstate")
    except Exception as exc:
        return {
            "exec_id": exec_id,
            "workflow_triggered": workflow_triggered,
            "workflow_error": workflow_error,
            "es_write": "failed",
            "error": str(exc),
        }

    return {
        "exec_id": exec_id,
        "workflow_triggered": workflow_triggered,
        "workflow_error": workflow_error,
        "es_write": "ok",
        "status": "pending",
        "message": (
            "Kibana Workflow triggered and action written to ES."
            if workflow_triggered else
            f"Action written to ES (Kibana Workflow {'not configured' if not workflow_id else 'failed: ' + (workflow_error or '')}). "
            "Runner will execute directly."
        ),
    }
