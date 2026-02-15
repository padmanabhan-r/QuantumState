# QuantumState — Data Model

## What are the fictional services?

QuantumState simulates a **fictional e-commerce platform**. The four services represent different parts of that platform:

| Service | What it does | Region |
|---|---|---|
| **payment-service** | Processes credit card charges, refunds, payment gateway communication. A memory leak here means transactions slow and eventually fail. | us-east-1 |
| **checkout-service** | Handles cart → order placement. Calls payment, inventory, and auth. A bug here breaks the entire purchase funnel. | us-east-1 |
| **auth-service** | Authenticates users via JWT + Redis session cache. Every service depends on it. Redis down → DB overwhelmed. | us-west-2 |
| **inventory-service** | Tracks stock, reserves items during checkout. EU warehouse. | eu-west-1 |

These are not running processes. They exist only as strings in Elasticsearch documents. See [`HOW_IT_WORKS.md`](HOW_IT_WORKS.md) for the full explanation.

---

## Indices

### 1. `metrics-quantumstate`

Time-series measurements. One document = one metric reading at one point in time.

| Field | Type | Description |
|---|---|---|
| `@timestamp` | date | When the measurement was taken |
| `service` | keyword | Service name (e.g. `payment-service`) |
| `region` | keyword | AWS region |
| `metric_type` | keyword | What is being measured (see below) |
| `value` | float | The numeric reading |
| `unit` | keyword | Unit of measurement |

**Metric types:**

| metric_type | unit | Healthy range | Alarm level |
|---|---|---|---|
| `memory_percent` | percent | 40–65% | >80% |
| `cpu_percent` | percent | 20–50% | >85% |
| `error_rate` | errors_per_min | <1/min | >10/min |
| `request_latency_ms` | ms | 80–200ms | >1000ms |
| `requests_per_min` | requests_per_min | 600–1000 | Dropping sharply |

---

### 2. `logs-quantumstate`

Application log lines. One document = one log entry.

| Field | Type | Description |
|---|---|---|
| `@timestamp` | date | When the log was emitted |
| `service` | keyword | Which service emitted it |
| `region` | keyword | Where it runs |
| `level` | keyword | INFO / WARN / ERROR / CRITICAL |
| `message` | text | The log text |
| `trace_id` | keyword | Request trace ID |
| `error_code` | keyword | Machine-readable error tag, null for INFO |

---

### 3. `incidents-quantumstate`

Pipeline-written incident records + pre-seeded historical incidents.

| Field | Type | Description |
|---|---|---|
| `@timestamp` | date | When the incident started |
| `service` | keyword | Affected service |
| `region` | keyword | Where it happened |
| `anomaly_type` | keyword | `memory_leak_progressive`, `error_spike_sudden`, `deployment_regression` |
| `root_cause` | text | Archaeologist's finding |
| `action_taken` | text | What the Surgeon described doing |
| `recommended_action` | keyword | `rollback_deployment`, `restart_service`, `scale_cache`, `restart_dependency` |
| `confidence_score` | float | Surgeon's confidence (0.0–1.0) |
| `risk_level` | keyword | `low`, `medium`, `high` |
| `resolution_status` | keyword | `RESOLVED`, `ESCALATE`, `PARTIALLY_RESOLVED`, `MONITORING` |
| `pipeline_run` | boolean | `true` if written by pipeline (not seed data) |
| `pipeline_summary` | text | One-line summary of the full pipeline run |
| `guardian_verified` | boolean | `true` after Guardian confirms recovery |
| `mttr_seconds` | integer | Seconds from incident open to Guardian RESOLVED verdict |
| `mttr_estimate` | keyword | Human-readable (e.g. `~4m 12s`) |
| `lessons_learned` | text | Surgeon's note for future runs |
| `resolved_at` | date | When the incident was resolved |

**Pre-seeded historical incidents** (loaded by Run Setup):

| Service | Type | Days ago | MTTR |
|---|---|---|---|
| payment-service | memory_leak_progressive | 14 | 47 min |
| auth-service | error_spike_sudden | 7 | 16 min |
| checkout-service | deployment_regression | 3 | 8 min |
| inventory-service | memory_leak_progressive | 21 | 90 min |

These let the Archaeologist say: *"This looks like the payment-service leak from 14 days ago. Last time, rolling back to v2.0.9 resolved it in 47 minutes."*

---

### 4. `agent-decisions-quantumstate`

Full audit trail. Every agent writes a record here when it makes a decision.

| Field | Type | Description |
|---|---|---|
| `@timestamp` | date | When the decision was made |
| `agent` | keyword | `cassandra`, `archaeologist`, `surgeon`, `guardian` |
| `decision` | text | What the agent decided, in plain text |
| `confidence` | integer | 0–100 |
| `service` | keyword | Which service this is about |
| `context` | object | Raw JSON blob — full input the agent received |

---

### 5. `remediation-actions-quantumstate`

One record per triggered remediation. Written by `/api/remediate` and the Kibana Workflow.

| Field | Type | Description |
|---|---|---|
| `@timestamp` | date | When the record was created |
| `exec_id` | keyword | Unique ID for this remediation (e.g. `b13c18fa`) |
| `incident_id` | keyword | Linked incident doc ID |
| `service` | keyword | Affected service |
| `action` | keyword | `rollback_deployment`, `restart_service`, `scale_cache`, `restart_dependency` |
| `anomaly_type` | keyword | What triggered it |
| `root_cause` | text | Archaeologist's root cause string |
| `confidence_score` | float | Surgeon's confidence |
| `risk_level` | keyword | `low`, `medium`, `high` |
| `triggered_by` | keyword | `autonomous` or `manual` |
| `status` | keyword | `pending`, `executing`, `executed`, `failed` |
| `executed_at` | date | When the action was marked executed |
| `workflow_triggered` | boolean | Whether the Kibana Workflow was called |
| `case_id` | keyword | Kibana Case ID created by the Workflow |

---

### 6. `remediation-results-quantumstate`

Guardian's post-verification records.

| Field | Type | Description |
|---|---|---|
| `@timestamp` | date | When Guardian ran |
| `exec_id` | keyword | Links to the remediation action |
| `service` | keyword | Verified service |
| `verdict` | keyword | `RESOLVED` or `ESCALATE` |
| `memory_pct` | float | Post-fix memory reading |
| `error_rate` | float | Post-fix error rate |
| `latency_ms` | float | Post-fix latency |
| `mttr_seconds` | integer | Time from incident to resolution |
| `confidence` | integer | Guardian's confidence in verdict |
| `summary` | text | One-sentence verdict summary |

---

### 7. `approval-requests-quantumstate`

Human-in-the-loop approval requests. Written by Tactician (roadmap agent) when risk is high.

| Field | Type | Description |
|---|---|---|
| `@timestamp` | date | When approval was requested |
| `service` | keyword | Service requiring approval |
| `proposed_action` | keyword | Action waiting for approval |
| `reason` | text | Why approval is required |
| `evidence_summary` | text | Supporting evidence from Archaeologist |
| `confidence_score` | float | Surgeon's confidence |
| `status` | keyword | `pending`, `approved`, `rejected` |
| `resolved_by` | keyword | Who approved/rejected |
| `resolved_at` | date | When it was resolved |

---

## How the indices connect

```
metrics-quantumstate         logs-quantumstate
      │                              │
      └──────────┬───────────────────┘
                 │ Cassandra queries both
                 ▼
         Anomaly detected
                 │
                 ▼
      Archaeologist queries:
        logs-quantumstate        (error logs for the affected service)
        incidents-quantumstate   (historical incidents for pattern match)
                 │
                 ▼
         Root cause identified
                 │
                 ▼
      Surgeon writes:
        incidents-quantumstate          (incident record)
        agent-decisions-quantumstate    (audit trail)
                 │
                 ▼ (if confidence ≥ 0.75)
      Remediation executes:
        remediation-actions-quantumstate  (action record, exec_id)
        metrics-quantumstate              (recovery metric documents)
        [Kibana Workflow creates Case]
                 │
                 ▼ (60 seconds later)
      Guardian queries:
        remediation-actions-quantumstate  (confirms exec_id)
        incidents-quantumstate            (gets incident timestamp for MTTR)
        metrics-quantumstate              (current metric averages)
      Guardian writes:
        incidents-quantumstate            (updates with verdict + MTTR)
        remediation-results-quantumstate  (full verification record)
        agent-decisions-quantumstate      (Guardian decision audit)
```

---

## The three demo scenarios

### Memory Leak → payment-service
- **Metrics:** `memory_percent` climbs 55% → 89% over 25 minutes
- **Logs:** WARN at 65%, ERROR at 80%, CRITICAL approaching 90% — error code `HEAP_PRESSURE`
- **Cassandra detects:** memory deviation >20% from 52% baseline
- **Archaeologist finds:** `HEAP_PRESSURE` error codes escalating over 30 min, no recent deploy, historical match (14 days ago same service)
- **Surgeon action:** `restart_service`
- **Recovery profile:** memory drops 85% → 54% over 7 minutes

### Deployment Regression → checkout-service
- **Metrics:** `error_rate` spikes 0.4 → 18/min within 3 minutes of deploy log
- **Logs:** Deploy event (`v3.5.0 complete`), then cascade of NPE stack traces — error code `INTERNAL_SERVER_ERROR`
- **Cassandra detects:** error rate >3/min
- **Archaeologist finds:** deploy log correlates exactly with spike, historical match 3 days ago
- **Surgeon action:** `rollback_deployment`
- **Recovery profile:** error rate drops 18 → 0.3/min over 7 minutes

### Error Spike → auth-service
- **Metrics:** `error_rate` jumps 0.3 → 28/min instantly, latency 95ms → 1200ms
- **Logs:** CRITICAL "Redis cluster node evicted — session cache OFFLINE" — error code `CACHE_OFFLINE`
- **Cassandra detects:** error rate >3/min
- **Archaeologist finds:** Redis failure log, historical incident 7 days ago with same pattern
- **Surgeon action:** `restart_dependency`
- **Recovery profile:** error rate drops 28 → 0.4/min, latency drops 1200ms → 120ms over 7 minutes
