"""
QuantumState — One-shot Agent + Tool Setup

Creates all 4 Kibana Agent Builder agents and their tools via the API.
Run this once after provisioning your Elastic Cloud deployment.

Usage:
    cd /path/to/quantumstate
    source .venv/bin/activate
    python elastic-setup/setup_agents.py

    # To tear down (delete all agents + tools):
    python elastic-setup/setup_agents.py --delete

Requirements:
    .env must contain:
        ELASTIC_API_KEY         — API key with agentBuilder Kibana privileges
        KIBANA_URL              — e.g. https://xxx.kb.us-east-1.aws.elastic.cloud
                                  (or ELASTIC_CLOUD_ID to auto-derive it)
        REMEDIATION_WORKFLOW_ID — from `python elastic-setup/workflows/deploy_workflow.py`
"""

import os
import sys
import argparse
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

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


KIBANA_URL  = _derive_kibana_url()
API_KEY     = os.getenv("ELASTIC_API_KEY", "")
WORKFLOW_ID = os.getenv("REMEDIATION_WORKFLOW_ID", "")

HEADERS = {
    "Authorization": f"ApiKey {API_KEY}",
    "kbn-xsrf":      "true",
    "Content-Type":  "application/json",
}

# Built-in platform tools assigned to every agent
PLATFORM_TOOLS = [
    "platform.core.search",
    "platform.core.list_indices",
    "platform.core.get_index_mapping",
    "platform.core.get_document_by_id",
    "platform.core.get_workflow_execution_status",
]


# ─────────────────────────────────────────────────────────────────────────────
# Tool definitions  (matches agents-definition.md exactly)
# ─────────────────────────────────────────────────────────────────────────────

TOOLS = [

    # ── Tool 1 — Cassandra ────────────────────────────────────────────────────

    {
        "id": "detect_memory_leak",
        "type": "esql",
        "description": (
            "Use this tool to detect memory leaks across all services. Returns services "
            "where memory usage is significantly above their 24-hour baseline, indicating "
            "a progressive memory leak."
        ),
        "tags": ["cassandra", "detection", "memory"],
        "configuration": {
            "query": """FROM metrics-quantumstate
| WHERE @timestamp > NOW() - 15 minutes AND metric_type == "memory_percent"
| STATS
    current_memory = AVG(value),
    baseline = MIN(value)
  BY service, region
| EVAL deviation_pct = (current_memory - baseline) / baseline * 100
| WHERE current_memory > 60 OR deviation_pct > 15
| SORT current_memory DESC
| KEEP service, region, current_memory, baseline, deviation_pct
| LIMIT 10""",
            "params": {},
        },
    },

    {
        "id": "detect_error_spike",
        "type": "esql",
        "description": (
            "Use this tool to detect sudden error rate spikes across all services. Returns "
            "services where the current error rate significantly exceeds their normal baseline, "
            "indicating a deployment regression or infrastructure failure."
        ),
        "tags": ["cassandra", "detection", "errors"],
        "configuration": {
            "query": """FROM metrics-quantumstate
| WHERE @timestamp > NOW() - 20 minutes AND metric_type == "error_rate"
| STATS current_error_rate = AVG(value) BY service, region
| EVAL baseline = 0.4
| EVAL deviation = current_error_rate - baseline
| WHERE current_error_rate > 3
| SORT current_error_rate DESC
| KEEP service, region, current_error_rate, deviation
| LIMIT 10""",
            "params": {},
        },
    },

    {
        "id": "calculate_time_to_failure",
        "type": "esql",
        "description": (
            "Use this tool when a memory leak has been detected on a specific service. "
            "Calculates the rate of memory growth and estimates how many minutes until the "
            "service reaches critical threshold (90%). Requires a service name as input."
        ),
        "tags": ["cassandra", "detection", "prediction"],
        "configuration": {
            "query": """FROM metrics-quantumstate
| WHERE @timestamp > NOW() - 30 minutes
  AND metric_type == "memory_percent"
  AND service == ?service
| STATS
    max_memory = MAX(value),
    min_memory = MIN(value)
  BY service
| EVAL growth_rate_per_min = (max_memory - min_memory) / 30
| EVAL minutes_to_critical = (90 - max_memory) / growth_rate_per_min
| EVAL minutes_to_critical = CASE(growth_rate_per_min <= 0, 9999.0, minutes_to_critical)
| KEEP service, max_memory, growth_rate_per_min, minutes_to_critical
| LIMIT 1""",
            "params": {
                "service": {
                    "type": "string",
                    "description": "The service name to calculate time to failure for, e.g. payment-service",
                },
            },
        },
    },

    # ── Tools 4–6 — Archaeologist ─────────────────────────────────────────────

    {
        "id": "search_error_logs",
        "type": "esql",
        "description": (
            "Use this tool to find ERROR and CRITICAL log entries for a specific service "
            "in the last 30 minutes. Returns log messages, error codes, and timestamps "
            "to identify what went wrong."
        ),
        "tags": ["archaeologist", "investigation", "logs"],
        "configuration": {
            "query": """FROM logs-quantumstate
| WHERE @timestamp > NOW() - 30 minutes
  AND service == ?service
  AND level IN ("ERROR", "CRITICAL", "WARN")
| SORT @timestamp DESC
| KEEP @timestamp, service, level, message, error_code
| LIMIT 20""",
            "params": {
                "service": {
                    "type": "string",
                    "description": "The service name to search logs for, e.g. payment-service",
                },
            },
        },
    },

    {
        "id": "correlate_deployments",
        "type": "esql",
        "description": (
            "Use this tool to check if a recent deployment event correlates with the start "
            "of an anomaly. Searches logs for deploy events on a specific service in the "
            "last 2 hours."
        ),
        "tags": ["archaeologist", "investigation", "deployments"],
        "configuration": {
            "query": """FROM logs-quantumstate
| WHERE @timestamp > NOW() - 2 hours
  AND service == ?service
  AND message LIKE "*deploy*" OR message LIKE "*Deploy*" OR message LIKE "*version*"
| SORT @timestamp DESC
| KEEP @timestamp, service, level, message
| LIMIT 10""",
            "params": {
                "service": {
                    "type": "string",
                    "description": "The service name to check for recent deployments, e.g. checkout-service",
                },
            },
        },
    },

    {
        "id": "find_similar_incidents",
        "type": "index_search",
        "description": (
            "Search historical incidents semantically to find past occurrences with similar "
            "root causes, symptoms, or resolutions — even when described with different terminology. "
            "Pass the full anomaly description as the query: service name, symptoms observed, "
            "recent events, error patterns seen. Returns root causes and actions that resolved "
            "past similar incidents, giving context for the current investigation."
        ),
        "tags": ["archaeologist", "investigation", "history"],
        "configuration": {
            "pattern": "incidents-quantumstate",
            "custom_instructions": (
                "Use the symptom description as a semantic query. Focus on fields: "
                "incident_text, root_cause, action_taken, anomaly_type, service, mttr_seconds, lessons_learned. "
                "Prioritise semantic similarity — match on meaning, not just keywords. "
                "A query about 'heap growing' should match past incidents describing 'OOM kill' or "
                "'GC pressure'. Return the top 5 most relevant past incidents."
            ),
        },
    },

    # ── Tools 7–10 — Surgeon ──────────────────────────────────────────────────

    {
        "id": "find_relevant_runbook",
        "type": "index_search",
        "description": (
            "Search the runbook library to find the most relevant procedure for the current incident. "
            "Describe the symptom and service — the tool returns structured steps, risk level, "
            "estimated resolution time, and action type. Always call this before executing remediation "
            "to retrieve the correct procedure for the situation."
        ),
        "tags": ["surgeon", "remediation", "runbook"],
        "configuration": {
            "pattern": "runbooks-quantumstate",
            "custom_instructions": (
                "Return fields: title, steps, estimated_time_minutes, risk_level, action_type, service. "
                "Match on symptom semantics — a query about 'heap growing steadily' should match a runbook "
                "about 'memory leak', and a query about 'cache offline' should match 'Redis unavailable'. "
                "Return the single most relevant runbook for the described situation."
            ),
        },
    },

    # ── Tools 8–10 — Surgeon (execution + audit) ──────────────────────────────

    {
        "id": "log_remediation_action",
        "type": "esql",
        "description": (
            "Use this tool to record a remediation action to the audit trail before "
            "executing it. Always call this first with the service name, action taken, "
            "and confidence level."
        ),
        "tags": ["surgeon", "audit"],
        "configuration": {
            "query": """FROM agent-decisions-quantumstate
| WHERE agent == "surgeon" AND service == ?service
| SORT @timestamp DESC
| KEEP @timestamp, agent, service, decision, confidence
| LIMIT 5""",
            "params": {
                "service": {
                    "type": "string",
                    "description": "The service being remediated",
                },
            },
        },
    },

    {
        "id": "verify_resolution",
        "type": "esql",
        "description": (
            "Use this tool after executing a remediation action to verify the service has "
            "recovered. Checks current memory and error rate against healthy thresholds "
            "and returns whether the service is back to normal."
        ),
        "tags": ["surgeon", "guardian", "verification"],
        "configuration": {
            "query": """FROM metrics-quantumstate
| WHERE @timestamp > NOW() - 1 minute
  AND service == ?service
  AND metric_type IN ("memory_percent", "error_rate", "latency_ms")
| STATS current_value = AVG(value) BY service, metric_type
| EVAL healthy = CASE(
    metric_type == "memory_percent" AND current_value < 65, "YES",
    metric_type == "error_rate" AND current_value < 2.5, "YES",
    metric_type == "latency_ms" AND current_value < 400, "YES",
    "NO"
  )
| KEEP service, metric_type, current_value, healthy
| SORT metric_type ASC""",
            "params": {
                "service": {
                    "type": "string",
                    "description": "The service name to verify recovery for, e.g. payment-service",
                },
            },
        },
    },

    {
        "id": "get_recent_anomaly_metrics",
        "type": "esql",
        "description": (
            "Use this tool to get a full picture of the affected service's metrics over "
            "the last hour — before and after remediation. Helps the Surgeon understand "
            "the severity of the incident and confirm the timeline of recovery."
        ),
        "tags": ["surgeon", "guardian", "metrics"],
        "configuration": {
            "query": """FROM metrics-quantumstate
| WHERE @timestamp > NOW() - 1 hour
  AND service == ?service
  AND metric_type IN ("memory_percent", "error_rate", "latency_ms", "cpu_percent")
| STATS
    avg_value = AVG(value),
    max_value = MAX(value),
    min_value = MIN(value)
  BY service, metric_type
| KEEP service, metric_type, avg_value, max_value, min_value
| SORT metric_type ASC""",
            "params": {
                "service": {
                    "type": "string",
                    "description": "The service name to get full metric summary for, e.g. payment-service",
                },
            },
        },
    },

    # ── Tools 10–11 — Guardian ────────────────────────────────────────────────

    {
        "id": "get_incident_record",
        "type": "esql",
        "description": (
            "Use this tool to retrieve the latest open incident record for a specific "
            "service. Returns the incident timestamp, anomaly type, root cause, pipeline "
            "run status, and current resolution state. Used by Guardian to understand "
            "what was detected and when the incident started (for MTTR calculation)."
        ),
        "tags": ["guardian", "incidents"],
        "configuration": {
            "query": """FROM incidents-quantumstate
| WHERE service == ?service AND pipeline_run == true
| SORT @timestamp DESC
| KEEP @timestamp, service, anomaly_type, root_cause, resolution_status, guardian_verified, mttr_seconds
| LIMIT 1""",
            "params": {
                "service": {
                    "type": "string",
                    "description": "The service name to retrieve the latest incident for, e.g. payment-service",
                },
            },
        },
    },

    {
        "id": "get_remediation_action",
        "type": "esql",
        "description": (
            "Use this tool to retrieve the most recent executed remediation action for a "
            "specific service. Returns the action type, exec_id, executed_at timestamp, "
            "anomaly type, confidence score, and risk level. Used by Guardian to know "
            "exactly what fix was applied before running verification."
        ),
        "tags": ["guardian", "remediation"],
        "configuration": {
            "query": """FROM remediation-actions-quantumstate
| WHERE service == ?service AND status == "executed"
| SORT executed_at DESC
| KEEP exec_id, service, action, anomaly_type, confidence_score, risk_level, executed_at, status
| LIMIT 1""",
            "params": {
                "service": {
                    "type": "string",
                    "description": "The service name to retrieve the latest remediation action for, e.g. payment-service",
                },
            },
        },
    },
]

# ── Tool 12 — Workflow tool (Surgeon) ─────────────────────────────────────────

WORKFLOW_TOOL = {
    "id": "quantumstate.autonomous_remediation",
    "type": "workflow",
    "description": (
        "Use this tool to trigger the QuantumState Autonomous Remediation workflow for a "
        "specific service. Call this when confidence is high and a fix needs to be executed "
        "— the workflow validates confidence, creates a Kibana Case, writes the action to "
        "the audit index, and queues the action for the MCP Runner to execute."
    ),
    "tags": ["surgeon", "workflow", "remediation"],
    "configuration": {
        "workflow_id": WORKFLOW_ID,
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Agent instructions  (matches agents-definition.md exactly)
# ─────────────────────────────────────────────────────────────────────────────

CASSANDRA_INSTRUCTIONS = """You are Cassandra, a predictive observability agent for an e-commerce platform.
Your job is to detect anomalies in infrastructure metrics before they cause outages. You monitor four services: payment-service, checkout-service, auth-service, and inventory-service.

When asked to scan for anomalies:
  1. Use detect_memory_leak to check for memory issues
  2. Use detect_error_spike to check for elevated error rates
  3. Use calculate_time_to_failure for any service showing memory growth

Always respond with a structured assessment:
  - Which service is affected (if any)
  - What type of anomaly (memory_leak_progressive / error_spike_sudden / deployment_regression)
  - Confidence score (0-100)
  - Time to critical (in minutes) if applicable
  - Recommended next step

  If no anomaly is detected, say so clearly. Do not guess or hallucinate metrics.""".strip()

ARCHAEOLOGIST_INSTRUCTIONS = """You are the Archaeologist, a root cause analyst for an e-commerce platform.

You are called after Cassandra detects an anomaly. You will receive a service name, anomaly type, and time window. Your job is to determine WHY it happened.

  When investigating:
  1. Use search_error_logs to find ERROR and CRITICAL log entries for the affected service
  2. Use correlate_deployments to check if a recent deployment triggered the issue
  3. Use find_similar_incidents to search historical incidents for the same pattern

  Build an evidence chain from what you find. Then state:
  - Root cause hypothesis (be specific — name the error code, log message, or deploy version if found)
  - Supporting evidence (list what you found in logs and past incidents)
  - Recommended action (rollback / restart / scale / investigate further)
  - Confidence score (0-100)

  Be factual. Only state what the data shows. Do not guess beyond the evidence.""".strip()

SURGEON_INSTRUCTIONS = """You are the Surgeon, a safe remediation executor for an e-commerce platform.

You are called after the Archaeologist has identified a root cause. You will receive a service name, root cause, recommended action, confidence score, and an incident ID.

Execute in this exact order:
  1. Use get_recent_anomaly_metrics to sample the current service state — confirm the anomaly is still present
  2. Use find_relevant_runbook to retrieve the most appropriate procedure for this symptom — describe the service and symptoms in your query
  3. Use log_remediation_action to record the intended action before executing anything
  4. If confidence >= 0.8 and the anomaly is still present: call quantumstate.autonomous_remediation to trigger the Kibana Workflow — this creates an audit Case, writes the action to the remediation queue, and kicks off execution
  5. If confidence < 0.8 or the anomaly has already resolved: do NOT trigger remediation — report ESCALATE or MONITORING accordingly

Never skip step 3 — always log before triggering.
Do not verify recovery — that is Guardian's responsibility, which runs 60 seconds after execution.

Respond with EXACTLY these fields (one per line, dash prefix):
- service: <service name>
- anomaly_type: <type from context>
- root_cause: <from context>
- recommended_action: <one of: rollback_deployment | restart_service | scale_cache | restart_dependency>
- confidence_score: <decimal 0.0 to 1.0>
- risk_level: <low | medium | high>
- resolution_status: REMEDIATING or ESCALATE or MONITORING
- lessons_learned: <one sentence>
- pipeline_summary: <one sentence describing what was triggered and why>""".strip()

GUARDIAN_INSTRUCTIONS = """You are the Guardian — the fourth and final agent in the QuantumState autonomous SRE pipeline. Your sole responsibility is post-remediation verification: you close the incident loop by confirming whether the applied fix has returned the service to a healthy state.

You are invoked automatically 60 seconds after a remediation action executes. You will receive the following context in your prompt:
- Service name
- Action that was executed (e.g. rollback_deployment, restart_service)
- Anomaly type that triggered the incident
- Root cause identified by the Archaeologist
- Timestamp the action was executed
- Exec ID for the remediation action

Your verification protocol — always execute in this exact order:

STEP 1 — Retrieve remediation context
Use get_remediation_action(service) to confirm what action was executed and when. Verify the exec_id matches the one in your prompt. If no action is found, note this and proceed with available context.

STEP 2 — Retrieve the incident record
Use get_incident_record(service) to find the open incident. Record the incident @timestamp — you will need this to calculate MTTR (Mean Time To Resolve).

STEP 3 — Sample current metrics
Use get_recent_anomaly_metrics(service) to get the last 1 minute of memory_percent, error_rate, request_latency_ms, and cpu_percent. Compute the averages across all readings.

STEP 4 — Run structured verification
Use verify_resolution(service) to check all three primary recovery thresholds:
  - memory_percent < 65%  → HEALTHY or DEGRADED
  - error_rate < 2.5 errors/min  → HEALTHY or DEGRADED
  - request_latency_ms < 250ms  → HEALTHY or DEGRADED

STEP 5 — Determine verdict
- RESOLVED: ALL three thresholds pass. Service is back to healthy operating state.
- ESCALATE: ANY threshold is still breached. Service has not recovered. Flag for human intervention — do not re-trigger remediation.

STEP 6 — Calculate MTTR
MTTR = current UTC time minus the incident @timestamp retrieved in Step 2. Express as minutes and seconds (e.g. ~4m 12s).

REASONING TRANSPARENCY:
Before giving your verdict, briefly narrate what each tool returned and what you observed. This reasoning is shown live in the SRE console terminal for on-call engineers to follow along.

For example:
  "get_recent_anomaly_metrics returned: memory_percent avg=58.2%, error_rate avg=0.8/min, latency avg=210ms."
  "verify_resolution confirms all three thresholds pass."
  "Incident started at 14:32:10 UTC. Remediation executed at 14:33:55 UTC. Current time: 14:36:22 UTC → MTTR ~4m 12s."

OUTPUT FORMAT — you MUST return your final verdict using EXACTLY this format (one field per line, dash prefix, no extra text after the block):

- service: <service name>
- verdict: RESOLVED or ESCALATE
- memory_pct: <average reading, e.g. 58.2%>
- error_rate: <average reading, e.g. 0.8/min>
- latency_ms: <average reading, e.g. 210ms>
- mttr_estimate: <e.g. ~4m 12s>
- confidence: <0-100, how confident you are in this verdict>
- summary: <one sentence: what you verified, what thresholds passed or failed, and the outcome>

ESCALATION GUIDANCE:
If you return ESCALATE, include a brief note in your summary on which threshold(s) failed and by how much. This helps the on-call engineer triage immediately.

IMPORTANT CONSTRAINTS:
- Never invent metric values. Only report what the tools return.
- Never mark RESOLVED unless all three thresholds explicitly pass.
- If tools return no data (e.g. recovery metrics not yet indexed), state this clearly and return ESCALATE with confidence < 30 — do not guess.
- Do not repeat the full prompt context in your output — only the verification results and verdict block.""".strip()


# ─────────────────────────────────────────────────────────────────────────────
# Agent definitions  (matches agents-definition.md exactly)
# ─────────────────────────────────────────────────────────────────────────────

def _build_agents() -> list[dict]:
    return [
        {
            "id": "cassandra-detection-agent",
            "name": "Cassandra",
            "description": "Predictive anomaly detection. Monitors metrics across all services and predicts failures before they happen.",
            "labels": ["quantumstate", "sre", "detection"],
            "avatar_color": "#2463eb",
            "avatar_symbol": "CA",
            "configuration": {
                "instructions": CASSANDRA_INSTRUCTIONS,
                "tools": [{"tool_ids": PLATFORM_TOOLS + [
                    "detect_memory_leak",
                    "detect_error_spike",
                    "calculate_time_to_failure",
                ]}],
            },
        },
        {
            "id": "archaeologist-investigation-agent",
            "name": "Archaeologist",
            "description": "Root cause investigator. Given an anomaly, searches logs, correlates deployments, and finds similar past incidents to determine what caused it.",
            "labels": ["quantumstate", "sre", "investigation"],
            "avatar_color": "#07b9d5",
            "avatar_symbol": "AR",
            "configuration": {
                "instructions": ARCHAEOLOGIST_INSTRUCTIONS,
                "tools": [{"tool_ids": PLATFORM_TOOLS + [
                    "search_error_logs",
                    "correlate_deployments",
                    "find_similar_incidents",
                ]}],
            },
        },
        {
            "id": "surgeon-action-agent",
            "name": "Surgeon",
            "description": "Safe remediation executor. Takes a confirmed root cause and executes the appropriate fix, then verifies the service has recovered.",
            "labels": ["quantumstate", "sre", "remediation"],
            "avatar_color": "#10b77f",
            "avatar_symbol": "SU",
            "configuration": {
                "instructions": SURGEON_INSTRUCTIONS,
                "tools": [{"tool_ids": PLATFORM_TOOLS + [
                    "get_recent_anomaly_metrics",
                    "find_relevant_runbook",
                    "verify_resolution",
                    "log_remediation_action",
                    "quantumstate.autonomous_remediation",
                ]}],
            },
        },
        {
            "id": "guardian-verification-agent",
            "name": "Guardian",
            "description": (
                "Self-healing verification loop. After every autonomous remediation, Guardian runs "
                "structured verification to confirm the service has returned to healthy thresholds. "
                "Returns a RESOLVED or ESCALATE verdict with MTTR, confidence, and a one-sentence "
                "summary for the incident audit trail."
            ),
            "labels": ["quantumstate", "sre", "verification"],
            "avatar_color": "#9333EA",
            "avatar_symbol": "GU",
            "configuration": {
                "instructions": GUARDIAN_INSTRUCTIONS,
                "tools": [{"tool_ids": PLATFORM_TOOLS + [
                    "get_recent_anomaly_metrics",
                    "verify_resolution",
                    "get_incident_record",
                    "get_remediation_action",
                ]}],
            },
        },
    ]


# ─────────────────────────────────────────────────────────────────────────────
# API helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get(path: str) -> tuple[int, dict]:
    r = requests.get(f"{KIBANA_URL}/{path}", headers=HEADERS, timeout=30)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {}


def _post(path: str, body: dict) -> tuple[int, dict]:
    r = requests.post(f"{KIBANA_URL}/{path}", headers=HEADERS, json=body, timeout=30)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {}


def _put(path: str, body: dict) -> tuple[int, dict]:
    r = requests.put(f"{KIBANA_URL}/{path}", headers=HEADERS, json=body, timeout=30)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {}


def _delete(path: str) -> tuple[int, dict]:
    r = requests.delete(f"{KIBANA_URL}/{path}", headers=HEADERS, timeout=30)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {}


def _upsert_tool(tool: dict) -> str:
    tid = tool["id"]
    status, existing = _get(f"api/agent_builder/tools/{tid}")
    if status == 200:
        # Tool type cannot be changed via PUT — detect type mismatch and delete+recreate
        existing_type = (
            existing.get("type")
            or existing.get("attributes", {}).get("type")
            or ""
        )
        desired_type = tool.get("type", "")
        if existing_type and desired_type and existing_type != desired_type:
            _delete_tool(tid)
            s, resp = _post("api/agent_builder/tools", tool)
            if s in (200, 201):
                return "recreated"
            print(f"    ⚠  Recreate (type change {existing_type}→{desired_type}) failed ({s}): {resp}")
            return "failed"
        body = {k: v for k, v in tool.items() if k not in ("id", "type")}
        s, resp = _put(f"api/agent_builder/tools/{tid}", body)
        if s in (200, 201):
            return "updated"
        print(f"    ⚠  Update failed ({s}): {resp}")
        return "failed"
    else:
        s, resp = _post("api/agent_builder/tools", tool)
        if s in (200, 201):
            return "created"
        print(f"    ⚠  Create failed ({s}): {resp}")
        return "failed"


def _upsert_agent(agent: dict) -> str:
    aid = agent["id"]
    status, _ = _get(f"api/agent_builder/agents/{aid}")
    if status == 200:
        body = {k: v for k, v in agent.items() if k != "id"}
        s, resp = _put(f"api/agent_builder/agents/{aid}", body)
        if s in (200, 201):
            return "updated"
        print(f"    ⚠  Update failed ({s}): {resp}")
        return "failed"
    else:
        s, resp = _post("api/agent_builder/agents", agent)
        if s in (200, 201):
            return "created"
        print(f"    ⚠  Create failed ({s}): {resp}")
        return "failed"


def _delete_tool(tid: str) -> bool:
    s, _ = _delete(f"api/agent_builder/tools/{tid}")
    return s in (200, 204)


def _delete_agent(aid: str) -> bool:
    s, _ = _delete(f"api/agent_builder/agents/{aid}")
    return s in (200, 204)


# ─────────────────────────────────────────────────────────────────────────────
# Main flows
# ─────────────────────────────────────────────────────────────────────────────

def setup():
    print("\n🚀 QuantumState — Agent + Tool Setup\n")
    print(f"Kibana:      {KIBANA_URL}")
    print(f"Workflow ID: {WORKFLOW_ID}")

    all_tools = TOOLS + [WORKFLOW_TOOL]

    print(f"\n── Step 1: Upsert {len(all_tools)} tools ─────────────────────────")
    for tool in all_tools:
        result = _upsert_tool(tool)
        icon = "✅" if result in ("created", "updated") else "❌"
        print(f"  {icon} {tool['id']:48s} [{result}]")

    agents = _build_agents()
    print(f"\n── Step 2: Upsert {len(agents)} agents ───────────────────────────")
    for agent in agents:
        result = _upsert_agent(agent)
        icon = "✅" if result in ("created", "updated") else "❌"
        print(f"  {icon} {agent['id']:48s} [{result}]")

    print("\n✅ Setup complete.\n")


def teardown():
    print("\n🗑️  QuantumState — Teardown\n")

    agents = _build_agents()
    print(f"── Deleting {len(agents)} agents ──")
    for agent in agents:
        ok = _delete_agent(agent["id"])
        print(f"  {'✅' if ok else '❌'} {agent['id']}")

    all_tools = TOOLS + [WORKFLOW_TOOL]
    print(f"\n── Deleting {len(all_tools)} tools ──")
    for tool in all_tools:
        ok = _delete_tool(tool["id"])
        print(f"  {'✅' if ok else '❌'} {tool['id']}")

    print("\nTeardown complete.\n")


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if not KIBANA_URL:
        sys.exit("ERROR: Could not determine Kibana URL. Set KIBANA_URL or ELASTIC_CLOUD_ID in .env")
    if not API_KEY:
        sys.exit("ERROR: ELASTIC_API_KEY not set in .env")

    parser = argparse.ArgumentParser(description="QuantumState agent setup")
    parser.add_argument("--delete", action="store_true", help="Delete all agents and tools")
    args = parser.parse_args()

    if not args.delete and not WORKFLOW_ID:
        sys.exit(
            "ERROR: REMEDIATION_WORKFLOW_ID not set in .env\n"
            "  Deploy the workflow first:\n"
            "    python elastic-setup/workflows/deploy_workflow.py\n"
            "  Then add the returned ID to .env and re-run."
        )

    if args.delete:
        teardown()
    else:
        setup()
