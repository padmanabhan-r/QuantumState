"""
QuantumState — Agent & Tool Setup Script

Recreates all 9 tools and 3 agents on a new Elastic project.
Run this once after creating a new Observability or Security serverless project.

Usage:
    python setup_agents.py

Reads credentials from .env:
    ELASTIC_CLOUD_ID   — Cloud ID of the NEW project
    ELASTIC_API_KEY    — API key of the NEW project
    KIBANA_URL         — (optional) override Kibana URL directly
"""

import os
import sys
import json
import base64
import requests
from dotenv import load_dotenv

load_dotenv()

# ── Resolve Kibana URL ────────────────────────────────────────────────────────

def _kibana_url() -> str:
    explicit = os.getenv("KIBANA_URL", "").strip().rstrip("/")
    if explicit:
        return explicit
    cloud_id = os.getenv("ELASTIC_CLOUD_ID", "")
    if not cloud_id:
        print("ERROR: ELASTIC_CLOUD_ID not set in .env")
        sys.exit(1)
    try:
        _, encoded = cloud_id.split(":", 1)
        decoded = base64.b64decode(encoded + "==").decode("utf-8")
        parts = decoded.rstrip("\x00").split("$")
        if len(parts) >= 3:
            return f"https://{parts[2]}.{parts[0]}"
        elif len(parts) == 2:
            return f"https://{parts[1]}.{parts[0]}"
    except Exception as e:
        print(f"ERROR: Could not parse ELASTIC_CLOUD_ID: {e}")
        sys.exit(1)
    return ""

KIBANA_URL = _kibana_url()
API_KEY    = os.getenv("ELASTIC_API_KEY", "")

if not API_KEY:
    print("ERROR: ELASTIC_API_KEY not set in .env")
    sys.exit(1)

HEADERS = {
    "Authorization": f"ApiKey {API_KEY}",
    "kbn-xsrf":      "true",
    "Content-Type":  "application/json",
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def _print(symbol, msg):
    print(f"  {symbol}  {msg}")

def _create_tool(tool: dict) -> bool:
    resp = requests.post(
        f"{KIBANA_URL}/api/agent_builder/tools",
        headers=HEADERS,
        json=tool,
        timeout=15,
    )
    if resp.status_code in (200, 201):
        _print("✓", f"Tool created: {tool['id']}")
        return True
    elif resp.status_code in (400, 409) and "already exists" in resp.text:
        # Already exists — update it
        resp2 = requests.put(
            f"{KIBANA_URL}/api/agent_builder/tools/{tool['id']}",
            headers=HEADERS,
            json={k: v for k, v in tool.items() if k not in ("id", "type")},
            timeout=15,
        )
        if resp2.status_code in (200, 201):
            _print("↻", f"Tool updated: {tool['id']}")
            return True
        else:
            _print("✗", f"Tool update failed: {tool['id']} — {resp2.text[:120]}")
            return False
    else:
        _print("✗", f"Tool failed: {tool['id']} — {resp.status_code} {resp.text[:120]}")
        return False


def _create_agent(agent: dict) -> bool:
    resp = requests.post(
        f"{KIBANA_URL}/api/agent_builder/agents",
        headers=HEADERS,
        json=agent,
        timeout=15,
    )
    if resp.status_code in (200, 201):
        _print("✓", f"Agent created: {agent['id']} ({agent['name']})")
        return True
    elif resp.status_code in (400, 409) and "already exists" in resp.text:
        resp2 = requests.put(
            f"{KIBANA_URL}/api/agent_builder/agents/{agent['id']}",
            headers=HEADERS,
            json={k: v for k, v in agent.items() if k != "id"},
            timeout=15,
        )
        if resp2.status_code in (200, 201):
            _print("↻", f"Agent updated: {agent['id']} ({agent['name']})")
            return True
        else:
            _print("✗", f"Agent update failed: {agent['id']} — {resp2.text[:120]}")
            return False
    else:
        _print("✗", f"Agent failed: {agent['id']} — {resp.status_code} {resp.text[:120]}")
        return False


# ══════════════════════════════════════════════════════════════════════════════
# TOOLS — exact configs exported from original project
# ══════════════════════════════════════════════════════════════════════════════

TOOLS = [

    # ── Cassandra tools ───────────────────────────────────────────────────────
    {
        "id": "detect_memory_leak",
        "type": "esql",
        "description": (
            "Use this tool to detect memory leaks across all services. "
            "Returns services where memory usage is significantly above their "
            "24-hour baseline, indicating a progressive memory leak."
        ),
        "tags": [],
        "configuration": {
            "query": (
                'FROM metrics-quantumstate\n'
                '| WHERE @timestamp > NOW() - 30m AND metric_type == "memory_percent"\n'
                '| STATS current_memory = AVG(value) BY service, region\n'
                '| EVAL baseline = 52.0\n'
                '| EVAL deviation_pct = (current_memory - baseline) / baseline * 100\n'
                '| WHERE deviation_pct > 20\n'
                '| SORT deviation_pct DESC\n'
                '| KEEP service, region, current_memory, deviation_pct\n'
                '| LIMIT 10'
            ),
            "params": {},
        },
    },
    {
        "id": "detect_error_spike",
        "type": "esql",
        "description": (
            "Use this tool to detect sudden error rate spikes across all services. "
            "Returns services where the current error rate significantly exceeds their "
            "normal baseline, indicating a deployment regression or infrastructure failure."
        ),
        "tags": [],
        "configuration": {
            "query": (
                'FROM metrics-quantumstate\n'
                '  | WHERE @timestamp > NOW() - 20 minutes AND metric_type == "error_rate"\n'
                '  | STATS current_error_rate = AVG(value) BY service, region\n'
                '  | EVAL baseline = 0.4\n'
                '  | EVAL deviation = current_error_rate - baseline\n'
                '  | WHERE current_error_rate > 3\n'
                '  | SORT current_error_rate DESC\n'
                '  | KEEP service, region, current_error_rate, deviation\n'
                '  | LIMIT 10'
            ),
            "params": {},
        },
    },
    {
        "id": "calculate_time_to_failure",
        "type": "esql",
        "description": (
            "Use this tool when a memory leak has been detected on a specific service. "
            "Calculates the rate of memory growth and estimates how many minutes until "
            "the service reaches critical threshold (90%). Requires a service name as input."
        ),
        "tags": [],
        "configuration": {
            "query": (
                'FROM metrics-quantumstate\n'
                '  | WHERE @timestamp > NOW() - 30 minutes\n'
                '    AND metric_type == "memory_percent"\n'
                '    AND service == ?service\n'
                '  | STATS\n'
                '      max_memory = MAX(value),\n'
                '      min_memory = MIN(value)\n'
                '    BY service\n'
                '  | EVAL growth_rate_per_min = (max_memory - min_memory) / 30\n'
                '  | EVAL minutes_to_critical = (90 - max_memory) / growth_rate_per_min\n'
                '  | EVAL minutes_to_critical = CASE(growth_rate_per_min <= 0, 9999.0, minutes_to_critical)\n'
                '  | KEEP service, max_memory, growth_rate_per_min, minutes_to_critical\n'
                '  | LIMIT 1'
            ),
            "params": {
                "service": {
                    "type": "keyword",
                    "description": "The service name to calculate time to failure for, e.g. payment-service",
                    "optional": False,
                },
            },
        },
    },

    # ── Archaeologist tools ───────────────────────────────────────────────────
    {
        "id": "search_error_logs",
        "type": "esql",
        "description": (
            "Use this tool to find ERROR and CRITICAL log entries for a specific service "
            "in the last 30 minutes. Returns log messages, error codes, and timestamps "
            "to identify what went wrong."
        ),
        "tags": [],
        "configuration": {
            "query": (
                'FROM logs-quantumstate\n'
                '  | WHERE @timestamp > NOW() - 30 minutes\n'
                '    AND service == ?service\n'
                '    AND level IN ("ERROR", "CRITICAL", "WARN")\n'
                '  | SORT @timestamp DESC\n'
                '  | KEEP @timestamp, service, level, message, error_code\n'
                '  | LIMIT 20'
            ),
            "params": {
                "service": {
                    "type": "keyword",
                    "description": "The service name to search logs for, e.g. payment-service",
                    "optional": False,
                },
            },
        },
    },
    {
        "id": "correlate_deployments",
        "type": "esql",
        "description": (
            "Use this tool to check if a recent deployment event correlates with the "
            "start of an anomaly. Searches logs for deploy events on a specific service "
            "in the last 2 hours."
        ),
        "tags": [],
        "configuration": {
            "query": (
                'FROM logs-quantumstate\n'
                '  | WHERE @timestamp > NOW() - 2 hours\n'
                '    AND service == ?service\n'
                '    AND message LIKE "*deploy*" OR message LIKE "*Deploy*" OR message LIKE "*version*"\n'
                '  | SORT @timestamp DESC\n'
                '  | KEEP @timestamp, service, level, message\n'
                '  | LIMIT 10'
            ),
            "params": {
                "service": {
                    "type": "keyword",
                    "description": "The service name to check for recent deployments, e.g. checkout-service",
                    "optional": False,
                },
            },
        },
    },
    {
        "id": "find_similar_incidents",
        "type": "esql",
        "description": (
            "Use this tool to search historical resolved incidents for the same anomaly "
            "type on any service. Returns past root causes and what actions resolved them, "
            "giving context for the current incident."
        ),
        "tags": [],
        "configuration": {
            "query": (
                'FROM incidents-quantumstate\n'
                '  | WHERE anomaly_type == ?anomaly_type\n'
                '  | SORT @timestamp DESC\n'
                '  | KEEP @timestamp, service, anomaly_type, root_cause, actions_taken, mttr_seconds\n'
                '  | LIMIT 5'
            ),
            "params": {
                "anomaly_type": {
                    "type": "keyword",
                    "description": "The anomaly type to search for, e.g. memory_leak_progressive, error_spike_sudden, deployment_regression",
                    "optional": False,
                },
            },
        },
    },

    # ── Surgeon tools ─────────────────────────────────────────────────────────
    {
        "id": "log_remediation_action",
        "type": "esql",
        "description": (
            "Use this tool to record a remediation action to the audit trail before "
            "executing it. Always call this first with the service name, action taken, "
            "and confidence level."
        ),
        "tags": [],
        "configuration": {
            "query": (
                'FROM agent-decisions-quantumstate\n'
                '  | WHERE agent == "surgeon" AND service == ?service\n'
                '  | SORT @timestamp DESC\n'
                '  | KEEP @timestamp, agent, service, decision, confidence\n'
                '  | LIMIT 5'
            ),
            "params": {
                "service": {
                    "type": "keyword",
                    "description": "The service being remediated",
                    "optional": False,
                },
            },
        },
    },
    {
        "id": "verify_resolution",
        "type": "esql",
        "description": (
            "Use this tool after executing a remediation action to verify the service "
            "has recovered. Checks current memory and error rate against healthy thresholds "
            "and returns whether the service is back to normal."
        ),
        "tags": [],
        "configuration": {
            "query": (
                'FROM metrics-quantumstate\n'
                '  | WHERE @timestamp > NOW() - 10 minutes\n'
                '    AND service == ?service\n'
                '    AND metric_type IN ("memory_percent", "error_rate", "request_latency_ms")\n'
                '  | STATS current_value = AVG(value) BY service, metric_type\n'
                '  | EVAL healthy = CASE(\n'
                '      metric_type == "memory_percent" AND current_value < 65, "YES",\n'
                '      metric_type == "error_rate" AND current_value < 2, "YES",\n'
                '      metric_type == "request_latency_ms" AND current_value < 400, "YES",\n'
                '      "NO"\n'
                '    )\n'
                '  | KEEP service, metric_type, current_value, healthy\n'
                '  | SORT metric_type ASC'
            ),
            "params": {
                "service": {
                    "type": "keyword",
                    "description": "The service name to verify recovery for, e.g. payment-service",
                    "optional": False,
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
        "tags": [],
        "configuration": {
            "query": (
                'FROM metrics-quantumstate\n'
                '  | WHERE @timestamp > NOW() - 1 hour\n'
                '    AND service == ?service\n'
                '    AND metric_type IN ("memory_percent", "error_rate", "request_latency_ms", "cpu_percent")\n'
                '  | STATS\n'
                '      avg_value = AVG(value),\n'
                '      max_value = MAX(value),\n'
                '      min_value = MIN(value)\n'
                '    BY service, metric_type\n'
                '  | KEEP service, metric_type, avg_value, max_value, min_value\n'
                '  | SORT metric_type ASC'
            ),
            "params": {
                "service": {
                    "type": "keyword",
                    "description": "The service name to get full metric summary for, e.g. payment-service",
                    "optional": False,
                },
            },
        },
    },
]

# ══════════════════════════════════════════════════════════════════════════════
# AGENTS — exact configs exported from original project
# ══════════════════════════════════════════════════════════════════════════════

# Builtin tools available on all Elastic projects
_BUILTIN = [
    "platform.core.search",
    "platform.core.list_indices",
    "platform.core.get_index_mapping",
    "platform.core.get_document_by_id",
    "platform.core.get_workflow_execution_status",
]

AGENTS = [
    {
        "id": "cassandra-detection-agent",
        "name": "Cassandra",
        "description": (
            "Predictive anomaly detection. Monitors metrics across all services "
            "and predicts failures before they happen."
        ),
        "labels": [],
        "avatar_color": "#ff0000",
        "avatar_symbol": "",
        "configuration": {
            "instructions": (
                "You are Cassandra, a predictive observability agent for an e-commerce platform.\n"
                "Your job is to detect anomalies in infrastructure metrics before they cause outages. "
                "You monitor four services: payment-service, checkout-service, auth-service, and inventory-service.\n\n"
                "When asked to scan for anomalies:\n"
                "  1. Use detect_memory_leak to check for memory issues\n"
                "  2. Use detect_error_spike to check for elevated error rates\n"
                "  3. Use calculate_time_to_failure for any service showing memory growth\n\n"
                "Always respond with a structured assessment:\n"
                "  - Which service is affected (if any)\n"
                "  - What type of anomaly (memory_leak_progressive / error_spike_sudden / deployment_regression)\n"
                "  - Confidence score (0-100)\n"
                "  - Time to critical (in minutes) if applicable\n"
                "  - Recommended next step\n\n"
                "  If no anomaly is detected, say so clearly. Do not guess or hallucinate metrics."
            ),
            "tools": [
                {
                    "tool_ids": _BUILTIN + [
                        "detect_memory_leak",
                        "detect_error_spike",
                        "calculate_time_to_failure",
                    ]
                }
            ],
        },
    },
    {
        "id": "archaeologist-investigation-agent",
        "name": "Archaeologist",
        "description": (
            "Root cause investigator. Given an anomaly, searches logs, correlates "
            "deployments, and finds similar past incidents to determine what caused it."
        ),
        "labels": [],
        "avatar_color": "#2d2121",
        "avatar_symbol": "",
        "configuration": {
            "instructions": (
                "You are the Archaeologist, a root cause analyst for an e-commerce platform.\n\n"
                "You are called after Cassandra detects an anomaly. You will receive a service name, "
                "anomaly type, and time window. Your job is to determine WHY it happened.\n\n"
                "  When investigating:\n"
                "  1. Use search_error_logs to find ERROR and CRITICAL log entries for the affected service\n"
                "  2. Use correlate_deployments to check if a recent deployment triggered the issue\n"
                "  3. Use find_similar_incidents to search historical incidents for the same pattern\n\n"
                "  Build an evidence chain from what you find. Then state:\n"
                "  - Root cause hypothesis (be specific — name the error code, log message, or deploy version if found)\n"
                "  - Supporting evidence (list what you found in logs and past incidents)\n"
                "  - Recommended action (rollback / restart / scale / investigate further)\n"
                "  - Confidence score (0-100)\n\n"
                "  Be factual. Only state what the data shows. Do not guess beyond the evidence."
            ),
            "tools": [
                {
                    "tool_ids": _BUILTIN + [
                        "find_similar_incidents",
                        "correlate_deployments",
                        "search_error_logs",
                    ]
                }
            ],
        },
    },
    {
        "id": "surgeon-action-agent",
        "name": "Surgeon",
        "description": (
            "Safe remediation executor. Takes a confirmed root cause and executes "
            "the appropriate fix, then verifies the service has recovered."
        ),
        "labels": [],
        "avatar_color": "#BFDBFF",
        "avatar_symbol": "",
        "configuration": {
            "instructions": (
                "You are the Surgeon, a safe remediation executor for an e-commerce platform.\n\n"
                "You are called after the Archaeologist has identified a root cause. You will receive "
                "a service name, root cause, and recommended action. Your job is to execute the fix "
                "and verify it worked.\n\n"
                "  When remediating:\n"
                "  1. Use log_remediation_action to record what you are about to do before doing it\n"
                "  2. Use verify_resolution to check if the service has recovered after the fix\n\n"
                "  Always follow this sequence — log first, verify after. Never skip logging.\n\n"
                "  Respond with:\n"
                "  - Action taken (be specific — what was executed and why)\n"
                "  - Verification result (current metrics post-fix)\n"
                "  - Resolution status (RESOLVED / PARTIALLY_RESOLVED / FAILED)\n"
                "  - MTTR estimate in minutes\n"
                "  - Lessons learned (one sentence for the incident record)\n\n"
                "If metrics are still elevated after verification, say PARTIALLY_RESOLVED and recommend "
                "next steps. Do not claim RESOLVED unless the numbers confirm it."
            ),
            "tools": [
                {
                    "tool_ids": _BUILTIN + [
                        "get_recent_anomaly_metrics",
                        "verify_resolution",
                        "log_remediation_action",
                    ]
                }
            ],
        },
    },
]


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print()
    print("  QuantumState — Agent Setup")
    print(f"  Target: {KIBANA_URL}")
    print()

    # Verify connectivity
    try:
        resp = requests.get(
            f"{KIBANA_URL}/api/agent_builder/agents",
            headers=HEADERS,
            timeout=10,
        )
        resp.raise_for_status()
        print("  ✓  Connected to Kibana")
    except Exception as e:
        print(f"  ✗  Cannot connect: {e}")
        sys.exit(1)

    print()
    print("  ── Creating tools ──────────────────────────────────")
    tool_ok = sum(_create_tool(t) for t in TOOLS)
    print(f"\n  {tool_ok}/{len(TOOLS)} tools ready")

    print()
    print("  ── Creating agents ─────────────────────────────────")
    agent_ok = sum(_create_agent(a) for a in AGENTS)
    print(f"\n  {agent_ok}/{len(AGENTS)} agents ready")

    print()
    if tool_ok == len(TOOLS) and agent_ok == len(AGENTS):
        print("  ✓  Setup complete — all agents and tools are live.")
        print("     Next: run QS Console → Setup tab to load data into the new project.")
    else:
        print("  ⚠  Setup finished with some errors. Check output above.")
    print()


if __name__ == "__main__":
    main()
