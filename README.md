# QuantumState

**Autonomous SRE agent swarm built on Elasticsearch. Detects production anomalies, traces root causes, executes remediations, and verifies recovery — fully closed loop, under 4 minutes.**

🌐 [Live Demo](https://www.quantumstate.online) · 🤖 [Agents Definition](agents-definition.md)

---

## The Problem

Imagine a backend service running in production. Memory usage starts climbing. At first, it looks harmless. Then it crosses a threshold. Latency spikes. Error rates rise. Alerts fire. At 3:00 AM, someone gets paged.

An SRE now has to:

- Check dashboards
- Query logs
- Correlate recent deployments
- Identify the root cause
- Decide on remediation (restart? rollback? scale?)
- Verify the system has recovered

Even with good observability, this process is manual, repetitive, and time-sensitive. MTTR increases not because data is unavailable — but because humans must interpret and act on it.

The real problem isn't detecting issues. It's turning detection into reliable, automated action.

---

## Introducing QuantumState

Most autonomous incident response systems work the same way: data flows out of your observability platform into an external AI layer, decisions get made somewhere else, and then actions are fired back through webhooks or APIs. You end up with external LLM API keys, custom orchestration middleware, fragile integrations — and your logs and metrics traveling across system boundaries on every incident.

QuantumState is built differently.

It is an autonomous SRE agent swarm built entirely on **[Elastic Agent Builder](https://www.elastic.co/docs/explore-analyze/ai-features/agent-builder/agent-builder-agents)** — Elastic's native framework for building and running AI agents directly inside your Elasticsearch cluster. Detection, investigation, remediation decisions, and verification all happen inside the platform where your data already lives. No data egress. No glue code. No external orchestration.

Four specialized agents run in sequence, each responsible for a distinct phase of the incident lifecycle:

1. **Detect** — Identify anomalies in metrics before they cascade.
2. **Investigate** — Correlate metrics and logs to determine the root cause.
3. **Execute** — Trigger a remediation action when confidence is high.
4. **Verify** — Confirm that system metrics have returned to baseline.

Instead of stopping at alerting, QuantumState carries the incident from detection to verified recovery — automatically, with a full audit trail written back to Elasticsearch at every step.

---

## Built on Elastic Agent Builder

**[Elastic Agent Builder](https://www.elastic.co/docs/explore-analyze/ai-features/agent-builder/agent-builder-agents)** lets you define agents — system prompts, tools, and workflow triggers — natively inside Kibana. The same configuration is fully accessible via the Kibana API for automation and CI/CD. For QuantumState, this means:

It lets you build agents directly inside the Elastic ecosystem — where your logs and metrics already live. Tools, system prompts, and workflow triggers are defined natively in Kibana with a clean UI, and the same configuration is fully accessible via the Kibana API for automation and CI/CD integration.

For QuantumState, this means:

- **No external LLM API keys** — agents run within your Elastic deployment
- **No orchestration middleware** — ES|QL queries are the agent tools; Elasticsearch is the reasoning substrate
- **No data egress** — detection, investigation, and remediation decision-making happen inside the cluster where the data lives
- **Full auditability** — every agent decision, tool call, and workflow trigger is written back to Elasticsearch

<img src="images/Elastic Agent Builder - Home.png" width="720" alt="Elastic Agent Builder Home" />

<img src="images/Elastic Agent Builder - New Agent.png" width="720" alt="Elastic Agent Builder New Agent" />

---

## The Agent Swarm

QuantumState uses four native Elastic Agent Builder agents — each responsible for a single stage of the incident lifecycle, each equipped with purpose-built ES|QL tools.

<img src="images/Web - The 4 Agents.png" width="720" alt="The 4 Agents" />

### 🔭 Cassandra — Detect

Continuously monitors system metrics using rolling time windows. Instead of relying on static thresholds, it compares current behavior against a dynamic baseline to detect gradual degradation — memory leaks, error spikes, latency drift — before they escalate into critical failures. Returns anomaly type, confidence score, and time-to-critical estimate.

**Tools:** `detect_memory_leak` · `detect_error_spike` · `calculate_time_to_failure`

### 🔍 Archaeologist — Investigate

Takes the anomaly context and correlates it with surrounding signals — logs, recent deployment events, and related system activity. Rather than identifying symptoms in isolation, it constructs an evidence chain linking cause to effect.

**Tools:** `search_error_logs` · `correlate_deployments` · `find_similar_incidents`

### ⚕️ Surgeon — Resolve

Evaluates possible remediation actions based on the detected anomaly and confidence score. Samples current service state, logs the intended action, then — if confidence ≥ 0.8 — calls `quantumstate.autonomous_remediation` directly to trigger the Kibana Workflow. The Workflow creates an audit Case and queues the action for the MCP Runner. Recovery verification is left to Guardian.

**Tools:** `log_remediation_action` · `get_recent_anomaly_metrics` · `verify_resolution` · `quantumstate.autonomous_remediation`

### 🛡️ Guardian — Verify

Closes the loop. After remediation, it validates whether system health has returned to baseline — checking memory, error rate, and latency thresholds. Returns `RESOLVED` or `ESCALATE` with a calculated MTTR. Only when recovery is confirmed does the incident lifecycle complete.

**Tools:** `get_recent_anomaly_metrics` · `verify_resolution` · `get_incident_record` · `get_remediation_action`

---

## The MCP Runner

The MCP Runner is the component that physically executes remediation. It acts as a lightweight sidecar that continuously polls for approved remediation actions written by the agents to Elasticsearch.

When an action is marked ready for execution, the MCP Runner performs the required infrastructure operation — restarting a container, triggering a rollback, scaling a cache dependency.

- No webhooks
- No external orchestration engines
- No separate automation platform

Elasticsearch acts as the coordination layer and message bus. The MCP Runner bridges agent decisions with real-world execution, keeping the architecture simple, auditable, and fully controlled within the Elastic ecosystem.

---

## Architecture & Pipeline Flow

At a high level, the flow is:

1. Metrics and logs stream continuously into Elasticsearch.
2. The Agent Pipeline orchestrates the four specialized agents.
3. When remediation is approved (confidence ≥ 0.8), an Elastic Workflow is triggered.
4. The Workflow records the action and maintains an auditable trail.
5. The MCP Runner executes the infrastructure action.
6. Guardian verifies recovery and closes the incident.

> Detection → Root Cause → Remediation → Verification → Closure

<img src="images/architecture-flow.svg" width="720" alt="Architecture Flow" />

---

## Setup

### Prerequisites

- Python 3.12+ · Node.js 18+
- Docker (for the real infrastructure demo)
- Elastic Cloud deployment

### Step 1: Elastic Cloud

Start with a free [14-day Elastic Cloud trial](https://cloud.elastic.co). Once provisioned, create an API key in Kibana and copy your Cloud ID.

Create a `.env` file in the project root:

```env
ELASTIC_CLOUD_ID=My_Project:base64encodedstring==
ELASTIC_API_KEY=your_api_key_here==
```

The Kibana URL is derived automatically from the Cloud ID. You'll add `REMEDIATION_WORKFLOW_ID` after the next step.

Then enable both features in **Stack Management → Advanced Settings**:

- `workflows:ui:enabled` — Elastic Workflows
- `agentBuilder:experimentalFeatures` — Elastic Agent Builder

This is a one-time step. Without it, the workflow deploy and agent setup will fail.

### Step 2: Deploy the Remediation Workflow

The workflow must exist before agents are created — the Surgeon agent requires its ID.

```bash
python elastic-setup/workflows/deploy_workflow.py
```

The script deploys `elastic-setup/workflows/remediation-workflow.yaml` to Kibana and prints the created workflow ID. Add it to `.env`:

```env
REMEDIATION_WORKFLOW_ID=workflow-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

Alternatively, create the workflow manually in the Kibana UI by importing `elastic-setup/workflows/remediation-workflow.yaml`.

### Step 3: Create Agents and Tools

```bash
python elastic-setup/setup_agents.py
```

Creates all 12 ES|QL tools and all 4 agents via the Kibana API in a single run. Idempotent — safe to re-run if you update instructions or tools.

```
── Step 1: Upsert 12 tools ──────────────────────────────
  ✅ detect_memory_leak                    [created]
  ✅ detect_error_spike                    [created]
  ✅ calculate_time_to_failure             [created]
  ✅ search_error_logs                     [created]
  ✅ correlate_deployments                 [created]
  ✅ find_similar_incidents                [created]
  ✅ log_remediation_action                [created]
  ✅ verify_resolution                     [created]
  ✅ get_recent_anomaly_metrics            [created]
  ✅ get_incident_record                   [created]
  ✅ get_remediation_action                [created]
  ✅ quantumstate.autonomous_remediation   [created]

── Step 2: Upsert 4 agents ───────────────────────────────
  ✅ cassandra-detection-agent             [created]
  ✅ archaeologist-investigation-agent     [created]
  ✅ surgeon-action-agent                  [created]
  ✅ guardian-verification-agent           [created]
```

If you prefer to set up agents manually, every agent ID, system prompt, tool assignment, and ES|QL query is documented in [`agents-definition.md`](agents-definition.md).

> **Verify in Kibana after setup.** Once the script completes, open Kibana → Agent Builder and confirm that all 4 agents appear with the correct tools assigned to each. Use [`agents-definition.md`](agents-definition.md) as the reference — it lists every agent's name, system prompt, and exact tool assignments. If anything looks wrong (missing tool, wrong prompt, incorrect ES|QL), edit it directly in the Kibana UI rather than re-running the script, as the UI gives you immediate feedback on what changed.

To tear everything down:

```bash
python elastic-setup/setup_agents.py --delete
```

<img src="images/Elastic Agent Builder - Agents List.png" width="720" alt="Elastic Agent Builder Agents List" />

### Step 4: Start the Application

```bash
git clone https://github.com/padmanabhan-r/QuantumState
cd QuantumState
uv sync
./start.sh
```

Launches the FastAPI backend on `http://localhost:8000` and the React frontend on `http://localhost:8080`.

---

## Running the Pipeline

### SRE Console

The Console is the main interface for running and observing the pipeline. Toggle **Auto Pipeline** on to run the full agent chain automatically on a schedule (90s locally, 3–5 min in production), or click **Run Pipeline** to trigger it immediately. Each agent's reasoning streams live to the terminal as it runs.

<!-- IMAGE: SRE Console screenshot -->

### Sim Control

Sim Control lets you manage the synthetic simulation environment without the Docker stack — set up indices, stream synthetic metrics, inject anomalies, and run the MCP Runner synthetically. Useful for quick testing without containers.

<!-- IMAGE: Sim Control screenshot -->

---

## Injecting Real Faults (Recommended)

The `infra/` directory contains a complete local microservice environment wired together via Docker Compose. Running this stack means the data Cassandra sees is real — actual memory allocation climbing inside a container, actual error logs being written, and an actual `docker restart` bringing memory back down.

```bash
cd infra
docker compose up --build
```

| Container | Port | Purpose |
|---|---|---|
| `payment-service` | 8001 | FastAPI service — memory leak target |
| `checkout-service` | 8002 | FastAPI service |
| `auth-service` | 8003 | FastAPI service — error spike target |
| `inventory-service` | 8004 | FastAPI service |
| `auth-redis` | 6379 | Redis dependency |
| `qs-scraper` | — | Polls `/health` every 15s → writes to `metrics-quantumstate` |
| `qs-mcp-runner` | — | Polls `remediation-actions-quantumstate` every 0.5s → `docker restart` |

Once up, the scraper immediately starts writing real readings to Elasticsearch. Cassandra has live data to work with.

#### Inject a fault

Use the TUI control panel:

```bash
uv run python infra/control.py
```

Press `1` to inject a memory leak into `payment-service`, `2` for an error spike into `auth-service`, `0` to reset everything.

Or via curl:

```bash
curl -X POST http://localhost:8001/simulate/leak
curl -X POST http://localhost:8003/simulate/spike?duration=600
curl -X POST http://localhost:8001/simulate/reset
```

#### What actually happens

When you inject a memory leak, `payment-service` allocates **4MB every 5 seconds** in real Python heap — not simulated. The scraper writes the rising readings to `metrics-quantumstate`. After ~30 seconds, the container starts emitting error logs:

```
ERROR HEAP_PRESSURE: JVM heap elevated: 58% — connection pool under pressure
WARN GC_OVERHEAD: GC overhead limit approaching: 63% heap utilised
CRITICAL OOM_IMMINENT: Out-of-memory condition imminent: 71% heap, GC unable to reclaim
```

These are the logs Archaeologist finds and builds its evidence chain from.

When Surgeon triggers remediation, the MCP Runner runs `docker restart payment-service`. The container restarts in 2–5 seconds. Memory drops back to baseline. The scraper writes the recovered readings. Guardian sees real recovery metrics.

The whole loop — memory climbing, detection, restart, recovery — is observable in real infrastructure.

#### Recommended trigger sequence

1. Start the Docker stack (`docker compose up --build` in `infra/`)
2. Wait ~2 minutes for baseline metrics to accumulate
3. Inject a fault via the TUI (`uv run python infra/control.py`)
4. Wait ~60–90 seconds for the fault to appear in the metrics index
5. Open `http://localhost:8080` → Console → **Run Pipeline**

---

## Demo

Here's the full pipeline running against a real memory leak injected into `payment-service`:

<!-- VIDEO: Full pipeline demo -->

1. Memory leak injected — `payment-service` allocates 4MB every 5s, memory climbs from ~42% to ~74%
2. Scraper writes real `/health` readings to `metrics-quantumstate` every 15s
3. Cassandra detects the deviation, calculates ~18 minutes to critical threshold
4. Archaeologist finds three correlated `HEAP_PRESSURE` and `OOM_IMMINENT` log entries
5. Surgeon evaluates confidence (0.91) — calls `quantumstate.autonomous_remediation` directly, triggering the Elastic Workflow
6. The Workflow creates a Kibana Case and writes the action to `remediation-actions-quantumstate` — the MCP Runner picks up the `pending` action within 0.5s and runs `docker restart payment-service`
7. Container restarts in ~3 seconds, memory drops to ~41%
8. Guardian verifies recovery against real post-restart metrics → **RESOLVED. MTTR: ~3m 48s**

The entire incident — real memory allocation, real container restart, real recovery — runs end-to-end without any human input.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Agent runtime | Elastic Agent Builder (Kibana) |
| Agent tools | ES\|QL — 12 custom parameterised queries |
| Workflow automation | Elastic Workflows (YAML, deployed via API) |
| Orchestration | Python FastAPI — SSE streaming |
| Data store | Elasticsearch Cloud |
| Frontend | React + Vite + TypeScript + shadcn/ui |

---

## Elasticsearch Indices

| Index | Purpose |
|---|---|
| `metrics-quantumstate` | Time-series CPU, memory, error rate, latency |
| `logs-quantumstate` | Application logs and deployment events |
| `incidents-quantumstate` | Full incident lifecycle records |
| `agent-decisions-quantumstate` | Agent decision audit trail |
| `remediation-actions-quantumstate` | Action queue polled by the MCP Runner |
| `remediation-results-quantumstate` | Guardian verdicts and post-fix metric readings |

All indices are created automatically the first time a document is written to them.

---

## Project Structure

```
quantumstate/
├── frontend/                   React + Vite + TypeScript UI
│   └── src/
│       ├── pages/              Index, Console, SimControl
│       └── components/         console/, landing/, ui/
├── backend/                    FastAPI Python backend
│   ├── main.py
│   ├── elastic.py              Shared ES client
│   ├── orchestrator.py         Agent Builder SSE streaming
│   └── routers/
│       ├── pipeline.py         4-agent orchestration
│       ├── guardian.py         Post-remediation verification
│       ├── remediate.py        Recovery metric writes
│       ├── sim.py              Simulation control
│       ├── incidents.py        Incident feed + MTTR stats
│       └── health.py           Live service health
├── elastic-setup/
│   ├── setup_agents.py         One-shot agent + tool provisioning
│   └── workflows/
│       ├── remediation-workflow.yaml
│       └── deploy_workflow.py
├── infra/                      Real Docker microservice environment
│   ├── services/               4 FastAPI services
│   ├── scraper/                Metrics scraper
│   ├── mcp-runner/             Real Docker remediation runner
│   └── docker-compose.yml
├── agents-definition.md        Full Kibana setup reference
├── start.sh                    Starts frontend + backend
└── .env                        Elastic credentials (not committed)
```
