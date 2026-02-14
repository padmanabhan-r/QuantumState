# QuantumState — Agent & Tool Definitions

Use this file to manually recreate all agents and tools in a new Elastic project.

---

## TOOLS (create these first)

Go to: **Agents → More → View all tools → New tool**

---

### Tool 1 — `detect_memory_leak`

| Field | Value |
|---|---|
| **Tool ID** | `detect_memory_leak` |
| **Type** | ES\|QL |
| **Description** | Use this tool to detect memory leaks across all services. Returns services where memory usage is significantly above their 24-hour baseline, indicating a progressive memory leak. |

**Query:**
```esql
FROM metrics-quantumstate
| WHERE @timestamp > NOW() - 30m AND metric_type == "memory_percent"
| STATS current_memory = AVG(value) BY service, region
| EVAL baseline = 52.0
| EVAL deviation_pct = (current_memory - baseline) / baseline * 100
| WHERE deviation_pct > 20
| SORT deviation_pct DESC
| KEEP service, region, current_memory, deviation_pct
| LIMIT 10
```

**Parameters:** none

---

### Tool 2 — `detect_error_spike`

| Field | Value |
|---|---|
| **Tool ID** | `detect_error_spike` |
| **Type** | ES\|QL |
| **Description** | Use this tool to detect sudden error rate spikes across all services. Returns services where the current error rate significantly exceeds their normal baseline, indicating a deployment regression or infrastructure failure. |

**Query:**
```esql
FROM metrics-quantumstate
| WHERE @timestamp > NOW() - 20 minutes AND metric_type == "error_rate"
| STATS current_error_rate = AVG(value) BY service, region
| EVAL baseline = 0.4
| EVAL deviation = current_error_rate - baseline
| WHERE current_error_rate > 3
| SORT current_error_rate DESC
| KEEP service, region, current_error_rate, deviation
| LIMIT 10
```

**Parameters:** none

---

### Tool 3 — `calculate_time_to_failure`

| Field | Value |
|---|---|
| **Tool ID** | `calculate_time_to_failure` |
| **Type** | ES\|QL |
| **Description** | Use this tool when a memory leak has been detected on a specific service. Calculates the rate of memory growth and estimates how many minutes until the service reaches critical threshold (90%). Requires a service name as input. |

**Query:**
```esql
FROM metrics-quantumstate
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
| LIMIT 1
```

**Parameters:**

| Name | Type | Required | Description |
|---|---|---|---|
| `service` | keyword | Yes | The service name to calculate time to failure for, e.g. `payment-service` |

---

### Tool 4 — `search_error_logs`

| Field | Value |
|---|---|
| **Tool ID** | `search_error_logs` |
| **Type** | ES\|QL |
| **Description** | Use this tool to find ERROR and CRITICAL log entries for a specific service in the last 30 minutes. Returns log messages, error codes, and timestamps to identify what went wrong. |

**Query:**
```esql
FROM logs-quantumstate
| WHERE @timestamp > NOW() - 30 minutes
  AND service == ?service
  AND level IN ("ERROR", "CRITICAL", "WARN")
| SORT @timestamp DESC
| KEEP @timestamp, service, level, message, error_code
| LIMIT 20
```

**Parameters:**

| Name | Type | Required | Description |
|---|---|---|---|
| `service` | keyword | Yes | The service name to search logs for, e.g. `payment-service` |

---

### Tool 5 — `correlate_deployments`

| Field | Value |
|---|---|
| **Tool ID** | `correlate_deployments` |
| **Type** | ES\|QL |
| **Description** | Use this tool to check if a recent deployment event correlates with the start of an anomaly. Searches logs for deploy events on a specific service in the last 2 hours. |

**Query:**
```esql
FROM logs-quantumstate
| WHERE @timestamp > NOW() - 2 hours
  AND service == ?service
  AND message LIKE "*deploy*" OR message LIKE "*Deploy*" OR message LIKE "*version*"
| SORT @timestamp DESC
| KEEP @timestamp, service, level, message
| LIMIT 10
```

**Parameters:**

| Name | Type | Required | Description |
|---|---|---|---|
| `service` | keyword | Yes | The service name to check for recent deployments, e.g. `checkout-service` |

---

### Tool 6 — `find_similar_incidents`

| Field | Value |
|---|---|
| **Tool ID** | `find_similar_incidents` |
| **Type** | ES\|QL |
| **Description** | Use this tool to search historical resolved incidents for the same anomaly type on any service. Returns past root causes and what actions resolved them, giving context for the current incident. |

**Query:**
```esql
FROM incidents-quantumstate
| WHERE anomaly_type == ?anomaly_type
| SORT @timestamp DESC
| KEEP @timestamp, service, anomaly_type, root_cause, actions_taken, mttr_seconds
| LIMIT 5
```

**Parameters:**

| Name | Type | Required | Description |
|---|---|---|---|
| `anomaly_type` | keyword | Yes | The anomaly type to search for, e.g. `memory_leak_progressive`, `error_spike_sudden`, `deployment_regression` |

---

### Tool 7 — `log_remediation_action`

| Field | Value |
|---|---|
| **Tool ID** | `log_remediation_action` |
| **Type** | ES\|QL |
| **Description** | Use this tool to record a remediation action to the audit trail before executing it. Always call this first with the service name, action taken, and confidence level. |

**Query:**
```esql
FROM agent-decisions-quantumstate
| WHERE agent == "surgeon" AND service == ?service
| SORT @timestamp DESC
| KEEP @timestamp, agent, service, decision, confidence
| LIMIT 5
```

**Parameters:**

| Name | Type | Required | Description |
|---|---|---|---|
| `service` | keyword | Yes | The service being remediated |

---

### Tool 8 — `verify_resolution`

| Field | Value |
|---|---|
| **Tool ID** | `verify_resolution` |
| **Type** | ES\|QL |
| **Description** | Use this tool after executing a remediation action to verify the service has recovered. Checks current memory and error rate against healthy thresholds and returns whether the service is back to normal. |

**Query:**
```esql
FROM metrics-quantumstate
| WHERE @timestamp > NOW() - 10 minutes
  AND service == ?service
  AND metric_type IN ("memory_percent", "error_rate", "request_latency_ms")
| STATS current_value = AVG(value) BY service, metric_type
| EVAL healthy = CASE(
    metric_type == "memory_percent" AND current_value < 65, "YES",
    metric_type == "error_rate" AND current_value < 2, "YES",
    metric_type == "request_latency_ms" AND current_value < 400, "YES",
    "NO"
  )
| KEEP service, metric_type, current_value, healthy
| SORT metric_type ASC
```

**Parameters:**

| Name | Type | Required | Description |
|---|---|---|---|
| `service` | keyword | Yes | The service name to verify recovery for, e.g. `payment-service` |

---

### Tool 9 — `get_recent_anomaly_metrics`

| Field | Value |
|---|---|
| **Tool ID** | `get_recent_anomaly_metrics` |
| **Type** | ES\|QL |
| **Description** | Use this tool to get a full picture of the affected service's metrics over the last hour — before and after remediation. Helps the Surgeon understand the severity of the incident and confirm the timeline of recovery. |

**Query:**
```esql
FROM metrics-quantumstate
| WHERE @timestamp > NOW() - 1 hour
  AND service == ?service
  AND metric_type IN ("memory_percent", "error_rate", "request_latency_ms", "cpu_percent")
| STATS
    avg_value = AVG(value),
    max_value = MAX(value),
    min_value = MIN(value)
  BY service, metric_type
| KEEP service, metric_type, avg_value, max_value, min_value
| SORT metric_type ASC
```

**Parameters:**

| Name | Type | Required | Description |
|---|---|---|---|
| `service` | keyword | Yes | The service name to get full metric summary for, e.g. `payment-service` |

---

## AGENTS (create after all tools are ready)

Go to: **Agents → Create agent**

---

### Agent 1 — Cassandra

| Field | Value |
|---|---|
| **Agent ID** | `cassandra-detection-agent` |
| **Name** | `Cassandra` |
| **Description** | Predictive anomaly detection. Monitors metrics across all services and predicts failures before they happen. |
| **Avatar colour** | `#FF0000` |

**System prompt:**
```
You are Cassandra, a predictive observability agent for an e-commerce platform.
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

If no anomaly is detected, say so clearly. Do not guess or hallucinate metrics.
```

**Tools to assign:**
- `platform.core.search` *(built-in)*
- `platform.core.list_indices` *(built-in)*
- `platform.core.get_index_mapping` *(built-in)*
- `platform.core.get_document_by_id` *(built-in)*
- `detect_memory_leak`
- `detect_error_spike`
- `calculate_time_to_failure`

---

### Agent 2 — Archaeologist

| Field | Value |
|---|---|
| **Agent ID** | `archaeologist-investigation-agent` |
| **Name** | `Archaeologist` |
| **Description** | Root cause investigator. Given an anomaly, searches logs, correlates deployments, and finds similar past incidents to determine what caused it. |
| **Avatar colour** | `#2D2121` |

**System prompt:**
```
You are the Archaeologist, a root cause analyst for an e-commerce platform.

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

  Be factual. Only state what the data shows. Do not guess beyond the evidence.
```

**Tools to assign:**
- `platform.core.search` *(built-in)*
- `platform.core.list_indices` *(built-in)*
- `platform.core.get_index_mapping` *(built-in)*
- `platform.core.get_document_by_id` *(built-in)*
- `search_error_logs`
- `correlate_deployments`
- `find_similar_incidents`

---

### Agent 3 — Surgeon

| Field | Value |
|---|---|
| **Agent ID** | `surgeon-action-agent` |
| **Name** | `Surgeon` |
| **Description** | Safe remediation executor. Takes a confirmed root cause and executes the appropriate fix, then verifies the service has recovered. |
| **Avatar colour** | `#BFDBFF` |

**System prompt:**
```
You are the Surgeon, a safe remediation executor for an e-commerce platform.

You are called after the Archaeologist has identified a root cause. You will receive a service name, root cause, and recommended action. Your job is to execute the fix and verify it worked.

  When remediating:
  1. Use log_remediation_action to record what you are about to do before doing it
  2. Use get_recent_anomaly_metrics to get the full picture of the service's state
  3. Use verify_resolution to check if the service has recovered after the fix

  Always follow this sequence — log first, verify after. Never skip logging.

  Respond with:
  - Action taken (be specific — what was executed and why)
  - Verification result (current metrics post-fix)
  - Resolution status (RESOLVED / PARTIALLY_RESOLVED / FAILED)
  - MTTR estimate in minutes
  - Lessons learned (one sentence for the incident record)

If metrics are still elevated after verification, say PARTIALLY_RESOLVED and recommend next steps. Do not claim RESOLVED unless the numbers confirm it.
```

**Tools to assign:**
- `platform.core.search` *(built-in)*
- `platform.core.list_indices` *(built-in)*
- `platform.core.get_index_mapping` *(built-in)*
- `platform.core.get_document_by_id` *(built-in)*
- `get_recent_anomaly_metrics`
- `verify_resolution`
- `log_remediation_action`
