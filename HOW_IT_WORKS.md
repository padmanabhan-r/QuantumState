# QuantumState — How It Actually Works (For AI Engineers)

You are not touching any real infrastructure. Nothing is being restarted. No pods are being killed. No code is being rolled back. Everything is a simulation running entirely inside Elasticsearch documents and AI agents reasoning about those documents.

Here is what is actually happening, layer by layer.

---

## The big picture in one sentence

**Elasticsearch is the entire universe.** The "production services" are documents. The "anomalies" are documents. The "fix" is writing recovery documents. The agents read documents and write documents. The frontend reads documents. Nothing outside Elasticsearch is real.

---

## What are the "services"?

There are no running services. `payment-service`, `checkout-service`, `auth-service`, and `inventory-service` do not exist as processes anywhere. They exist as **strings** in Elasticsearch documents.

When you click "Inject Memory Leak on payment-service", the backend runs `inject.py` which writes ~25 Elasticsearch documents that look like this:

```json
{ "@timestamp": "2026-02-15T03:47:00Z", "service": "payment-service", "metric_type": "memory_percent", "value": 67.3 }
{ "@timestamp": "2026-02-15T03:48:00Z", "service": "payment-service", "metric_type": "memory_percent", "value": 69.1 }
{ "@timestamp": "2026-02-15T03:49:00Z", "service": "payment-service", "metric_type": "memory_percent", "value": 71.4 }
...
{ "@timestamp": "2026-02-15T04:12:00Z", "service": "payment-service", "metric_type": "memory_percent", "value": 88.8 }
```

That is a "memory leak". It is a sequence of numbers going up. The documents also include corresponding log lines:

```json
{ "service": "payment-service", "level": "ERROR", "message": "JVM heap critical: 87.2%", "error_code": "HEAP_PRESSURE" }
```

There is no JVM. There is no heap. There is a JSON document with the string `"HEAP_PRESSURE"` in a field.

---

## What are the "agents"?

The agents are **LLMs running inside Kibana** (Elastic Agent Builder). Each agent has:
- A system prompt that tells it what role to play
- A set of tools (ES|QL queries) it can call
- Access to no external systems whatsoever — only Elasticsearch

When the pipeline runs, the FastAPI backend calls the Kibana Agent Builder `converse/async` API endpoint, which is an SSE stream. This is like calling `chat/completions` but the model has tools (ES|QL queries), and the API streams back the response token by token.

The agent is just an LLM. It reasons, calls its ES|QL tools, reads the results, and writes a structured text response. That's all.

---

## What does Cassandra actually do?

Cassandra is an LLM. When the pipeline runs, our backend sends it a prompt:

> "Scan all services for anomalies."

Cassandra's tools are ES|QL queries like this:

```esql
FROM metrics-quantumstate
| WHERE @timestamp > NOW() - 30m AND metric_type == "memory_percent"
| STATS current_memory = AVG(value) BY service, region
| EVAL baseline = 52.0
| EVAL deviation_pct = (current_memory - baseline) / baseline * 100
| WHERE deviation_pct > 20
```

This query runs against the documents we injected. It returns `payment-service` with `deviation_pct = 70.8`. Cassandra reads that number, reasons about it, and writes:

```
anomaly_detected: true
anomaly_type: memory_leak_progressive
confidence: 95
```

No detection algorithm. No ML model. Just an LLM reading ES|QL query results.

---

## What does the Archaeologist actually do?

The Archaeologist is an LLM. It receives Cassandra's output as its prompt:

> "Investigate payment-service. Anomaly: memory_leak_progressive. Time window: last 30 minutes."

Its tools search the log documents we injected:

```esql
FROM logs-quantumstate
| WHERE @timestamp > NOW() - 30 minutes AND service == "payment-service"
  AND level IN ("ERROR", "CRITICAL", "WARN")
| SORT @timestamp DESC
```

This returns the log documents containing `HEAP_PRESSURE`. The Archaeologist reads those strings and concludes "JVM heap exhaustion". It also queries historical incidents to find similar past events.

There is no log parsing algorithm. The Archaeologist is just an LLM reading documents.

---

## What does the Surgeon actually do?

The Surgeon is an LLM. It receives the Archaeologist's output. It calls `log_remediation_action` (reads the audit index), calls `get_recent_anomaly_metrics` (reads metrics), calls `verify_resolution` (checks if thresholds pass).

It reads all that, reasons about it, and writes:

```
action_taken: Initiated pod restart for payment-service
recommended_action: restart_service
confidence_score: 0.88
resolution_status: PARTIALLY_RESOLVED
```

**No pod is restarted.** The Surgeon writes text describing an action as if it happened.

---

## What does "remediation" actually do?

When the Surgeon outputs `recommended_action: restart_service` with confidence ≥ 0.75, the backend (`pipeline.py`) parses that text output and calls `_maybe_trigger_remediation()`.

This function:
1. Calls `POST /api/remediate` which writes a "recovery profile" — ~32 new metric documents with values that go from high back down to normal
2. Calls `POST /api/workflow/trigger` which hits the Kibana Workflow API to create a Kibana Case (a ticket in Kibana's case management system)

The recovery documents look like this:

```json
{ "@timestamp": "now+0min", "service": "payment-service", "metric_type": "memory_percent", "value": 85.2 }
{ "@timestamp": "now+1min", "service": "payment-service", "metric_type": "memory_percent", "value": 78.4 }
{ "@timestamp": "now+2min", "service": "payment-service", "metric_type": "memory_percent", "value": 71.1 }
...
{ "@timestamp": "now+7min", "service": "payment-service", "metric_type": "memory_percent", "value": 54.3 }
```

That is the "remediation". We wrote documents showing recovery. Nothing else changed.

---

## What does Guardian actually do?

Guardian is an LLM. It runs 60 seconds after remediation and checks if those recovery documents we just wrote are actually in a healthy range.

It calls:
- `get_remediation_action` → reads the action record from `remediation-actions-quantumstate`
- `get_incident_record` → reads the incident from `incidents-quantumstate`, gets the timestamp for MTTR
- `get_recent_anomaly_metrics` → averages the last 10 minutes of metrics
- `verify_resolution` → checks if averages are below thresholds

If the averages are below threshold → `RESOLVED`. If not → `ESCALATE`.

The ESCALATE you saw earlier happened because Guardian checked immediately after remediation. The recovery documents are timestamped `now` to `now+7min` — they hadn't fully propagated into the 10-minute average yet. Wait 5 minutes and run Guardian again, it would return RESOLVED.

---

## What is Elastic Workflow?

The Kibana Workflow (`QuantumState — Autonomous Remediation`) is a YAML-defined automation that runs inside Kibana when triggered. We deploy it via `POST /api/workflows`.

When we trigger it via `POST /api/workflows/{id}/run`, it:
1. Creates a Kibana Case (a ticket/incident record in Kibana's case management UI)
2. Writes a document to `remediation-actions-quantumstate`
3. Writes an audit doc to `agent-decisions-quantumstate`

This is the one real piece — it actually creates a visible Case in your Kibana UI. Everything else is documents and LLM text.

---

## How does this compare to the reference project?

The reference project (Augmented Infrastructure) solves a **different problem**: how to give a Kibana agent access to external tools (Docker, AWS, your filesystem) that Kibana can't reach natively.

Their pattern:
```
Kibana Agent → writes tool request to ES → Python runner polls ES → executes via MCP → writes result back to ES → Kibana Agent reads result
```

MCP (Model Context Protocol) is just a standard way to expose tools to LLMs — like OpenAI's function calling but cross-platform. Their runner has Docker MCP, time MCP, etc., letting the agent run `docker ps` on your machine.

**Our pattern is simpler and more vertical:**
```
FastAPI → calls Kibana Agent via SSE → agents use built-in ES|QL tools → agents hand off via structured text → FastAPI orchestrates the chain
```

We don't need MCP because our tools are all ES|QL queries (Kibana-native). We don't need an external runner because we're not touching external systems. The reference project's complexity is justified when you want the agent to actually SSH into servers, run kubectl, or call AWS APIs. We don't need that because our "infrastructure" is documents.

**Are we "good enough"?** For this hackathon: yes. Our system demonstrates:
- Multi-agent orchestration with hand-off
- Real Kibana Agent Builder agents with real tool calls
- Elastic Workflows as automation
- A closed loop (detect → investigate → remediate → verify)
- A live streaming UI showing the entire reasoning chain

The reference project is more general-purpose infrastructure. We are a focused, polished, end-to-end demo of one specific use case.

---

## The full flow, no hand-waving

```
1. You click "Inject Memory Leak"
   → inject.py writes 25 metric docs + 20 log docs to Elasticsearch
   → nothing else changes

2. You click "Run Pipeline"
   → FastAPI sends a prompt to cassandra-detection-agent via Kibana API
   → Cassandra calls detect_memory_leak (ES|QL query against our docs)
   → Cassandra returns structured text
   → FastAPI streams that text to your browser via SSE

3. FastAPI takes Cassandra's output, builds a prompt for archaeologist-investigation-agent
   → Archaeologist calls search_error_logs, correlate_deployments, find_similar_incidents
   → All three are ES|QL queries reading our documents
   → Archaeologist returns structured text
   → FastAPI streams to browser

4. FastAPI takes Archaeologist's output, builds a prompt for surgeon-action-agent
   → Surgeon calls log_remediation_action, get_recent_anomaly_metrics, verify_resolution
   → All ES|QL queries
   → Surgeon returns structured text including recommended_action + confidence_score
   → FastAPI streams to browser

5. FastAPI parses Surgeon's text output (regex on "recommended_action: restart_service")
   → If confidence >= 0.75:
     → Calls Kibana Workflow API (creates a Kibana Case)
     → Writes 32 recovery metric documents to Elasticsearch (the "fix")
     → Writes 1 action record to remediation-actions-quantumstate

6. 60 seconds later (or when you click "Verify with Guardian"):
   → FastAPI sends a prompt to guardian-verification-agent
   → Guardian calls 4 tools (all ES|QL reads)
   → Guardian checks if the recovery docs we wrote are below thresholds
   → Guardian returns RESOLVED or ESCALATE
   → FastAPI updates the incident document with verdict + MTTR
   → Browser shows the verdict card
```

That is the entire system. It is Elasticsearch documents + LLMs reading those documents + a React UI showing what the LLMs said.

---

## Why this is still impressive

The non-obvious part is not the data — it's the **coordination**:
- Each agent does structured reasoning using real data
- The hand-off chain (Cassandra output → Archaeologist prompt → Surgeon prompt → Guardian prompt) is designed so each agent has exactly the context it needs
- The Kibana Workflow is a real production artifact that creates traceable Case records
- The MTTR is real (time from incident doc timestamp to Guardian verification)
- The closed loop — detect, investigate, act, verify — mirrors how a real SRE would work

The simulation is a pragmatic shortcut for a hackathon demo. In a real deployment you would point the same agents at real metrics from APM, Elastic Agent fleet, or cloud monitoring. The agents, tools, and workflow would be identical.
