# QuantumState

**Autonomous SRE agent swarm. Detects production anomalies, traces root causes, executes remediations, and verifies recovery — fully closed loop, under 4 minutes.**

Built for the **Elastic Agent Builder Hackathon** (Jan 22 – Feb 27, 2026).

> Not an SRE? Read [`HOW_IT_WORKS.md`](HOW_IT_WORKS.md) for a plain-English explanation of what's actually happening under the hood.

---

## The problem

A memory leak starts at 3am. Your on-call engineer gets paged. They spend 47 minutes correlating dashboards, grepping logs, finding the deploy that caused it, deciding to rollback, executing it, and confirming the service recovered.

QuantumState does the same thing in under 4 minutes — autonomously, with a full audit trail.

---

## Four agents, one closed loop

```
Elasticsearch (metrics + logs)
         │
         ▼
┌─────────────────────┐
│  📡 Cassandra        │  Detection — ES|QL anomaly scan, time-to-failure forecast
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  🔬 Archaeologist    │  Investigation — log search, deployment correlation, historical match
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  🩺 Surgeon          │  Remediation — selects action, triggers Elastic Workflow
└──────────┬──────────┘
           │  (autonomous if confidence ≥ 0.75)
           ▼
  ⚡ Remediation executes
  Kibana Case created
  Recovery metrics written
           │
           ▼
┌─────────────────────┐
│  🛡️ Guardian         │  Verification — post-fix metric check, MTTR calc, RESOLVED/ESCALATE
└─────────────────────┘
           │
           ▼
  incidents-quantumstate (closed incident record with MTTR)
```

All four agents are **native Elastic Agent Builder agents** — no external LLM API keys, no external orchestration framework. Everything runs inside your Elastic cluster.

---

## Tech stack

| Layer | Technology |
|---|---|
| Agent runtime | Elastic Agent Builder (Kibana) |
| Agent tools | ES\|QL — 11 custom parameterised queries |
| Workflow automation | Elastic Workflows (YAML, deployed via API) |
| Orchestration | Python FastAPI — SSE streaming |
| Data store | Elasticsearch Serverless / Cloud |
| Frontend | React + Vite + TypeScript + shadcn/ui |

---

## Agents

### 📡 Cassandra — Detection
**ID:** `cassandra-detection-agent` · **Colour:** `#2463eb`

Runs ES|QL window-function queries comparing current metrics to a rolling 24h baseline. Detects memory leaks, error spikes, deployment regressions. Returns anomaly type, confidence score, and time-to-critical estimate.

**Tools:** `detect_memory_leak`, `detect_error_spike`, `calculate_time_to_failure`

---

### 🔬 Archaeologist — Investigation
**ID:** `archaeologist-investigation-agent` · **Colour:** `#07b9d5`

Searches error logs for the affected service, correlates deployment events that overlap the anomaly window, and queries historical incidents for similar failure patterns. Builds an evidence chain and identifies root cause.

**Tools:** `search_error_logs`, `correlate_deployments`, `find_similar_incidents`

---

### 🩺 Surgeon — Remediation
**ID:** `surgeon-action-agent` · **Colour:** `#10b77f`

Selects the appropriate remediation action (rollback, restart, cache scale, dependency restart). Samples pre-fix metrics for comparison. Triggers the Elastic Workflow if confidence ≥ threshold. Writes the full incident record.

**Tools:** `log_remediation_action`, `get_recent_anomaly_metrics`, `verify_resolution`

---

### 🛡️ Guardian — Verification
**ID:** `guardian-verification-agent` · **Colour:** `#b643ef`

Runs 60 seconds post-remediation. Retrieves the action record and incident timestamp, samples current metrics, checks all three recovery thresholds (memory < 65%, error rate < 2/min, latency < 250ms). Returns `RESOLVED` or `ESCALATE` with MTTR.

**Tools:** `get_remediation_action`, `get_incident_record`, `get_recent_anomaly_metrics`, `verify_resolution`, `quantumstate.autonomous_remediation` (Workflow tool)

---

## Elastic Workflow

`QuantumState — Autonomous Remediation` is a Kibana Workflow deployed via `POST /api/workflows`. When triggered by the Surgeon it:
1. Validates confidence score ≥ 0.8
2. Creates a Kibana Case with full incident context
3. Writes the action to `remediation-actions-quantumstate`
4. Writes an audit record to `agent-decisions-quantumstate`

Deploy: `python elastic-setup/workflows/deploy_workflow.py`

---

## Elasticsearch indices

| Index | Purpose |
|---|---|
| `metrics-quantumstate` | Time-series metrics — CPU, memory, error rate, latency |
| `logs-quantumstate` | Application logs with severity, trace IDs, error codes |
| `incidents-quantumstate` | Incident records — pipeline output + historical seed data |
| `agent-decisions-quantumstate` | Full audit trail of every agent decision |
| `remediation-actions-quantumstate` | Executed remediations with exec_id and workflow status |
| `remediation-results-quantumstate` | Guardian verdicts and post-fix metric readings |
| `approval-requests-quantumstate` | Human approval requests (Tactician — roadmap) |

---

## Project structure

```
quantumstate/
├── frontend/                   React + Vite + TypeScript UI
│   └── src/
│       ├── pages/              Index, Console, SimControl
│       └── components/         console/, landing/, ui/
├── backend/                    FastAPI Python backend
│   ├── main.py                 App entry, lifespan, router registration
│   ├── elastic.py              Shared ES client
│   ├── inject.py               Anomaly injection functions
│   ├── orchestrator.py         Agent Builder SSE streaming
│   └── routers/
│       ├── pipeline.py         4-agent orchestration + autonomous remediation trigger
│       ├── guardian.py         Guardian SSE endpoint + background verification worker
│       ├── remediate.py        Recovery metric writes + workflow trigger
│       ├── sim.py              Simulation control (setup, stream, inject, cleanup)
│       ├── incidents.py        Incident feed + MTTR stats
│       ├── health.py           Live service health aggregations
│       └── chat.py             Direct agent chat endpoint
├── elastic-setup/
│   └── workflows/
│       ├── remediation-workflow.yaml
│       └── deploy_workflow.py
├── agents-definition.md        Full Kibana setup reference (agents, tools, prompts)
├── HOW_IT_WORKS.md             Plain-English explanation for non-SREs
├── data-model.md               Index schemas, field definitions, demo scenarios
├── start.sh                    Starts frontend + backend
└── .env                        Elastic credentials (not committed)
```

---

## Live deployment

| | |
|---|---|
| **Frontend** | https://quantumstate.online |
| **Backend API** | https://quantumstate-backend-production.up.railway.app |

Frontend on Vercel · Backend on Railway

---

## Real infrastructure (v0.3.0)

`infra/` contains the real Docker services that the MCP runner operates against:

```
infra/
├── services/base/        # FastAPI service containers (payment, checkout, auth, inventory)
│   ├── main.py           # /health, /simulate/leak, /simulate/spike, /simulate/reset
│   └── Dockerfile
├── scraper/              # Polls /health every 10s, writes to metrics-quantumstate
│   └── scraper.py
├── mcp-runner/           # Polls remediation-actions, executes docker restart via SDK
│   ├── runner.py
│   └── Dockerfile
└── docker-compose.yml    # All 7 containers: 4 services + Redis + scraper + runner
```

Start the full local infra:

```bash
cd infra && docker compose up -d
```

Inject a real memory leak:

```bash
curl -X POST http://localhost:8001/simulate/leak
# Watch memory climb in docker stats
# Run pipeline in Console → Guardian RESOLVED with real MTTR
```

**Proven results:**
- Memory leak → `docker restart payment-service` → Guardian RESOLVED. **MTTR: ~8m**
- Error spike → `docker stop+start checkout-service` → Guardian RESOLVED. **MTTR: ~2m**

---

## Getting started

### Prerequisites
- Python 3.12+ · Node.js 18+
- Docker (for real infrastructure demo)
- Elastic Cloud deployment with Agent Builder enabled
- All 4 agents + 12 tools created in Kibana (see `agents-definition.md`)

### Environment

```env
ELASTIC_CLOUD_ID=your-cloud-id
ELASTIC_API_KEY=your-api-key
KIBANA_URL=https://your-deployment.kb.us-east-1.aws.elastic.cloud
REMEDIATION_WORKFLOW_ID=workflow-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
AUTONOMOUS_MODE=true
REMEDIATION_CONFIDENCE_THRESHOLD=0.75
SELF_BASE_URL=https://your-backend.up.railway.app   # backend self-reference URL (Railway/production)
```

### Run

```bash
./start.sh
```

| URL | What |
|---|---|
| http://localhost:8080 | Landing page |
| http://localhost:8080/console | SRE Console |
| http://localhost:8080/sim | Simulation Control |
| http://localhost:8000 | FastAPI API |

---

## Demo sequence

### Synthetic demo (Sim Control)
1. **Sim Control → Run Setup** — creates indices, seeds 24h baseline + 4 historical incidents
2. **Sim Control → Start Stream** — live metrics every 30s
3. **Sim Control → Inject → Memory Leak (payment-service)**
4. **Console → Run Pipeline** — watch all 4 agents stream live
5. **Console → Verify with Guardian** — purple button appears after remediation
6. **Console → Actions tab** — executed action with exec_id
7. **Console → Incidents tab** — closed incident with MTTR

### Real infrastructure demo
1. `cd infra && docker compose up -d`
2. `curl -X POST http://localhost:8001/simulate/leak`
3. Wait ~3 min for scraper to detect rising memory
4. **Console → Run Pipeline** → Surgeon autonomous remediation fires
5. MCP runner executes `docker restart payment-service`
6. **Console → Verify with Guardian** → RESOLVED

---

## Hackathon context

**Event:** Elastic Agent Builder Hackathon · **Prize pool:** $20,000
**Tracks:** Multi-agent systems + Time-series anomaly detection
**Measured outcome:** MTTR reduced from ~47 minutes (manual) to 7m 53s (autonomous, real infrastructure)
