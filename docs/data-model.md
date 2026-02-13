# QuantumState — Data Model

## What are the fictional services?

QuantumState simulates a **fictional e-commerce platform** — think something like Amazon, Shopify, or any company that runs microservices in production. The four services represent different parts of that platform:

| Service | What it does (in the fictional company) |
|---|---|
| **payment-service** | Processes credit card charges, refunds, and payment gateway communication. High-value, latency-sensitive. A memory leak here means transactions slow down and eventually fail. |
| **checkout-service** | Handles the shopping cart → order placement flow. It calls payment-service, inventory-service, and auth-service. A bug here breaks the entire purchase funnel. |
| **auth-service** | Authenticates users — validates JWT tokens, manages sessions via Redis cache. Every other service depends on it. When Redis goes down, auth falls back to the database and gets overwhelmed. |
| **inventory-service** | Tracks stock levels, reserves items during checkout. Runs in the EU region because the fictional company has a European warehouse. |

These aren't real services running on your machine — they exist only as **documents in Elasticsearch**. The Python scripts generate realistic metric and log data that looks exactly like what these services would produce if they were real.

---

## The Four Indices

### 1. `metrics-quantumstate`

Time-series numbers. Every metric is one document representing a single measurement at a point in time.

```
@timestamp          When this measurement was taken
service             Which service produced it (e.g. "payment-service")
region              Where it runs (e.g. "us-east-1")
metric_type         What is being measured (see table below)
value               The numeric reading
unit                What unit the value is in
```

**Metric types:**

| metric_type | unit | What it means | Healthy range | Alarm level |
|---|---|---|---|---|
| `memory_percent` | percent | JVM / container heap usage | 40–65% | >80% |
| `cpu_percent` | percent | CPU utilisation | 20–50% | >85% |
| `error_rate` | errors_per_min | Requests returning 5xx errors | <1/min | >10/min |
| `request_latency_ms` | ms | p95 response time | 80–200ms | >1000ms |
| `requests_per_min` | requests_per_min | Throughput | 600–1000 | Dropping sharply |

**Example document:**
```json
{
  "@timestamp": "2026-02-13T14:32:00Z",
  "service": "payment-service",
  "region": "us-east-1",
  "metric_type": "memory_percent",
  "value": 74.3,
  "unit": "percent"
}
```

---

### 2. `logs-quantumstate`

Application log lines. One document per log entry.

```
@timestamp          When the log was emitted
service             Which service emitted it
region              Where it runs
level               Severity: INFO / WARN / ERROR / CRITICAL
message             The actual log text
trace_id            Request trace ID (for correlating logs to a request)
error_code          Machine-readable error tag, null for INFO logs
```

**Log levels used:**

| level | When it appears |
|---|---|
| `INFO` | Normal operation — health checks, successful requests |
| `WARN` | Something degrading but not yet broken — elevated memory, slow queries |
| `ERROR` | A request failed — 5xx errors, exceptions, connection failures |
| `CRITICAL` | Service-level failure — cache offline, DB unreachable |

**Example document (during memory leak):**
```json
{
  "@timestamp": "2026-02-13T14:45:00Z",
  "service": "payment-service",
  "region": "us-east-1",
  "level": "ERROR",
  "message": "JVM heap critical: 87.2% — GC overhead limit approaching",
  "trace_id": "trace-482910",
  "error_code": "HEAP_PRESSURE"
}
```

---

### 3. `incidents-quantumstate`

Historical resolved incidents. This is the "institutional memory" the Archaeologist agent uses to find similar past events and recommend actions that worked before.

```
@timestamp          When the incident started
service             Which service was affected
region              Where it happened
anomaly_type        Classification of the failure pattern
root_cause          Full explanation of what caused it
actions_taken       What was done to fix it
resolved_at         When it was resolved
mttr_seconds        Mean Time To Resolve in seconds
status              Always "resolved" (open incidents go elsewhere)
```

**Pre-seeded incidents** (loaded by setup):

| Service | Type | Days ago | MTTR |
|---|---|---|---|
| payment-service | memory_leak_progressive | 14 days | 47 min |
| auth-service | error_spike_sudden | 7 days | 16 min |
| checkout-service | deployment_regression | 3 days | 8 min |
| inventory-service | memory_leak_progressive | 21 days | 90 min |

These let the Archaeologist say things like: *"This looks like the memory leak from 14 days ago. Last time, rolling back to v2.0.9 resolved it in 47 minutes."*

---

### 4. `agent-decisions-quantumstate`

The audit trail. Every time an agent makes a decision, it writes a record here. This is how you can prove the system worked and show judges what reasoning happened.

```
@timestamp          When the agent made this decision
agent               Which agent (cassandra / archaeologist / surgeon)
decision            What the agent decided, in plain text
confidence          How confident it was (0–100)
service             Which service this decision was about
context             Raw JSON blob — the full input the agent received
```

**Example document:**
```json
{
  "@timestamp": "2026-02-13T14:48:00Z",
  "agent": "cassandra",
  "decision": "Memory leak detected on payment-service. Current: 87%, baseline: 52%. Rate: +1.3%/min. Time to critical: ~10 minutes. Confidence: 94%.",
  "confidence": 94,
  "service": "payment-service",
  "context": { "anomaly_type": "memory_leak_progressive", "region": "us-east-1" }
}
```

---

## How the indices connect

```
metrics-quantumstate         logs-quantumstate
      │                              │
      │  Cassandra queries both      │
      │  looking for anomalies       │
      └──────────┬───────────────────┘
                 │
                 ▼
      Anomaly detected
      (service + time window)
                 │
                 ▼
      Archaeologist queries:
      ┌──────────────────────────────┐
      │ logs-quantumstate            │  ← search for ERROR/CRITICAL logs
      │   WHERE service = X          │     in the same time window
      │   AND @timestamp ~ anomaly   │
      └──────────────────────────────┘
      ┌──────────────────────────────┐
      │ incidents-quantumstate       │  ← find similar past incidents
      │   WHERE anomaly_type LIKE X  │     to recommend what worked before
      └──────────────────────────────┘
                 │
                 ▼
      Root cause identified
                 │
                 ▼
      Surgeon executes fix
      Writes result to:
      ┌──────────────────────────────┐
      │ agent-decisions-quantumstate │  ← full audit trail of all decisions
      └──────────────────────────────┘
```

---

## The three demo scenarios

Each scenario is a different failure pattern that gets injected as backdated documents:

### memory-leak → payment-service
- Metrics: `memory_percent` climbs 55% → 89% over 25 minutes
- Logs: WARN at 65%, ERROR at 80%, CRITICAL approaching 90%
- Error code: `HEAP_PRESSURE`
- Detection: Cassandra sees memory deviation >15% from baseline
- Archaeologist finds: similar incident 14 days ago on the same service

### deployment-rollback → checkout-service
- Metrics: `error_rate` spikes 0.4 → 18/min within 3 min of a deploy log
- Logs: Deploy event (INFO "v3.5.0 complete"), then cascade of NPE stack traces
- Error code: `INTERNAL_SERVER_ERROR`
- Detection: Cassandra sees error spike
- Archaeologist finds: deploy log correlates with spike, past incident 3 days ago

### error-spike → auth-service
- Metrics: `error_rate` jumps 0.3 → 28/min instantly, latency 95ms → 1200ms
- Logs: CRITICAL "Redis cluster node evicted — session cache OFFLINE"
- Error code: `CACHE_OFFLINE` / `REDIS_UNAVAILABLE`
- Detection: Cassandra sees error rate > 10/min
- Archaeologist finds: Redis-related incident 7 days ago, recommends restart + circuit breaker
