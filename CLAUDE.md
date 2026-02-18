# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

QuantumState is an autonomous SRE agent swarm that detects, investigates, and auto-remediates production incidents using Elasticsearch, ES|QL, ELSER, and Elastic Agent Builder. The system consists of **4 native Kibana Agent Builder agents** that run inside your Elastic cluster — no external LLM API keys required.

## Committing

- NEVER add Co-Authored-By to commit messages

## Development Commands

### Environment Setup
```bash
# Activate virtual environment
source .venv/bin/activate

# Install/update dependencies
pip install elasticsearch python-dotenv requests faker pandas numpy

# Configure Elastic credentials (create .env file)
# Required vars: ELASTIC_CLOUD_ID, ELASTIC_API_KEY
# Optional: ELASTIC_URL (for local Docker), KIBANA_URL, SELF_BASE_URL, REMEDIATION_WORKFLOW_ID
```

### Elastic Stack Setup (run in order)
```bash
# 1. Deploy ELSER sparse embedding model (required for semantic search)
python elastic-setup/setup_elser.py

# 2. Deploy the Kibana remediation workflow
python elastic-setup/workflows/deploy_workflow.py
# → copy the printed workflow ID into .env as REMEDIATION_WORKFLOW_ID

# 3. Start the app, open http://localhost:8080, go to Simulation & Setup → Run Setup
#    Creates all 7 indices and seeds historical incidents + 8 runbooks
./start.sh

# 4. Provision all 13 tools and 4 agents via Kibana API
python elastic-setup/setup_agents.py
```

### Running the Application
```bash
# Start frontend + backend together
./start.sh

# Or start individually:
cd backend && uvicorn main:app --port 8000 --reload
cd frontend && npm run dev
```

## Architecture

### Agent Swarm Pattern

The system uses **4 native Elastic Agent Builder agents**, orchestrated by a Python FastAPI backend via SSE streaming. The pipeline calls each agent sequentially, passing the prior agent's output as context:

1. **Cassandra** (Detection) — ES|QL queries detect anomalies in metrics; returns anomaly type, confidence, and time-to-failure estimate
2. **Archaeologist** (Investigation) — Searches logs, correlates deployments, uses ELSER hybrid search to surface similar historical incidents; returns root cause and evidence chain
3. **Surgeon** (Remediation) — Retrieves relevant runbook via ELSER, samples metrics, triggers the Elastic Workflow (confidence ≥ 0.8); autonomous if threshold met
4. **Guardian** (Verification) — Runs 60–90s post-remediation; checks memory, error rate, and latency thresholds; returns `RESOLVED` or `ESCALATE` with MTTR

**Roadmap agents** (not yet in pipeline): Tactician (decision/approval gate), Diplomat (human comms).

**Key concept**: The FastAPI orchestrator in `backend/routers/pipeline.py` calls each Kibana agent in turn via `converse_stream()`. Agents are provisioned via `elastic-setup/setup_agents.py` which hits the Kibana API. There are no Python agent classes — all agent logic lives in Kibana as system prompts + ES|QL/Index Search tools.

### Agent Tools

Each agent has purpose-built Kibana tools of two types:

- **ES|QL tools** — parameterised queries against Elasticsearch indices
- **Index Search tools** — ELSER-powered semantic search (used by Archaeologist's `find_similar_incidents` and Surgeon's `find_relevant_runbook`)
- **Workflow tool** — `quantumstate.autonomous_remediation` triggers the Kibana Workflow (Surgeon only)

### MCP Runner

The MCP Runner (`infra/mcp-runner/runner.py`) polls `remediation-actions-quantumstate` for `status: "pending"` and executes real `docker restart` via the Docker socket. A synthetic in-process runner is also available at `/api/sim/mcp-runner/execute` for non-Docker setups.

### Data Indices

| Index | Purpose |
|---|---|
| `metrics-quantumstate` | Time-series metrics — CPU, memory, error rate, latency |
| `logs-quantumstate` | Application logs with severity, trace IDs, error codes |
| `incidents-quantumstate` | Incident records + ELSER `semantic_text` field (`incident_text`) |
| `agent-decisions-quantumstate` | Full audit trail of every agent decision |
| `remediation-actions-quantumstate` | Executed remediations — picked up by MCP Runner |
| `remediation-results-quantumstate` | Guardian verdicts and post-fix metric readings |
| `runbooks-quantumstate` | 8 runbooks with ELSER `semantic_text` for hybrid retrieval |

## Key Patterns

### ES|QL Detection Queries

Detection queries compare peak values against a baseline using a split-window approach:

```esql
FROM metrics-quantumstate
| WHERE @timestamp > NOW() - 5 minutes AND metric_type == "memory_percent"
| STATS
    current_memory = AVG(value),
    peak_memory    = MAX(value)
  BY service, region
| EVAL deviation_pct = (peak_memory - current_memory) / current_memory * 100
| WHERE peak_memory > 65 OR deviation_pct > 25
| SORT peak_memory DESC
| KEEP service, region, current_memory, peak_memory, deviation_pct
| LIMIT 10
```

Using `MAX(value)` instead of `AVG` prevents signal dilution from averaging — progressive leaks are caught within ~3 minutes of injection rather than only at near-saturation.

### ELSER Hybrid Search

Two Index Search tools use ELSER semantic embeddings:

- `find_similar_incidents` (Archaeologist) — searches `incidents-quantumstate` on `incident_text` field; "heap growing" matches past incidents about "GC pressure" or "OOM kill"
- `find_relevant_runbook` (Surgeon) — searches `runbooks-quantumstate`; retrieves the most relevant procedure for the failure mode before triggering remediation

ELSER must be deployed before creating these tools (`python elastic-setup/setup_elser.py`).

### Pipeline Orchestration

`backend/routers/pipeline.py` manages the 4-agent chain:

1. A `threading.Lock` prevents concurrent pipeline runs (race condition on dedup check)
2. Cassandra empty-output guard — stops pipeline early with a descriptive message if Cassandra returns nothing
3. Status-driven dedup — `REMEDIATING < 15 min` blocks; `RESOLVED < 3 min` blocks (ghost cooldown); everything else passes through
4. `_maybe_trigger_remediation()` — parses Surgeon output; if `resolution_status == REMEDIATING` (Surgeon already fired the Workflow tool), emits SSE events; otherwise falls back to direct `/api/workflow/trigger`

### Environment Configuration

```python
from dotenv import load_dotenv
load_dotenv()

es = Elasticsearch(
    cloud_id=os.getenv('ELASTIC_CLOUD_ID'),
    api_key=os.getenv('ELASTIC_API_KEY'),
)
```

For local Docker deployments, use `ELASTIC_URL` instead of `ELASTIC_CLOUD_ID`.

## Project Structure

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
│   ├── orchestrator.py         Agent Builder converse_stream + _write_incident
│   └── routers/
│       ├── pipeline.py         4-agent SSE orchestration + remediation trigger
│       ├── remediate.py        Recovery metric writes + workflow trigger
│       ├── sim.py              Simulation control + synthetic MCP runner
│       ├── incidents.py        Incident feed + MTTR stats
│       ├── health.py           Live service health aggregations
│       └── chat.py             Direct agent chat endpoint
├── elastic-setup/
│   ├── setup_agents.py         Provisions all 13 tools + 4 agents via Kibana API
│   ├── setup_elser.py          Deploys .elser-2-elasticsearch inference endpoint
│   ├── seed_runbooks.py        Creates runbooks-quantumstate + seeds 8 runbooks
│   └── workflows/
│       ├── remediation-workflow.yaml
│       └── deploy_workflow.py
├── infra/
│   ├── docker-compose.yml      4 services + Redis + scraper + MCP runner
│   ├── services/               FastAPI containers (payment, checkout, auth, inventory)
│   ├── scraper/                Polls /health, writes to metrics-quantumstate
│   ├── mcp-runner/             Polls ES for pending actions, runs docker restart
│   └── control.py              TUI control panel for real-infra demo
├── images/                     Screenshots for README / agents-definition.md
├── agents-definition.md        Full Kibana setup reference (agents, tools, prompts)
├── start.sh                    Starts frontend + backend
└── .env                        Elastic credentials (not committed)
```

## Common Scenarios

### Adding a New ES|QL Tool to an Agent

1. Test the query in Kibana Dev Tools first
2. Add the tool definition to `TOOLS` list in `elastic-setup/setup_agents.py`
3. Update the agent's system prompt in the same file to instruct when to call it
4. Re-run `python elastic-setup/setup_agents.py` (it patches existing tools, creates new ones)

### Adding a New Agent

1. Add the agent definition (ID, name, colour, system prompt) to `elastic-setup/setup_agents.py`
2. Add its tool IDs to the agent's tool list in the same file
3. Add it to the orchestration flow in `backend/routers/pipeline.py`
4. Update `AGENT_IDS` dict in `pipeline.py`

### Creating a New Anomaly Injection

1. Add injection function to `backend/inject.py`
2. Use `latency_ms` (not `request_latency_ms`) for the latency field — must match scraper schema
3. Inject both metrics AND corresponding logs to enable Archaeologist correlation
4. Register the scenario in `backend/routers/sim.py`

### Modifying Detection Thresholds

Detection thresholds exist in two places and must be kept in sync:
- `elastic-setup/setup_agents.py` — ES|QL query `WHERE` clause
- `backend/routers/pipeline.py` — `CASSANDRA_PROMPT` (natural-language description for the agent)

## Dependencies

Core dependencies (see `pyproject.toml`):
- `elasticsearch>=8.11.0` — ES client with ES|QL support
- `python-dotenv` — Environment variable management
- `faker`, `pandas`, `numpy` — Data generation

Requires Python 3.12+ (see `.python-version`).

## Elasticsearch Requirements

- **ES|QL** requires ES 8.x+
- **ELSER v2 (`semantic_text`)** requires ES 8.11+
- **Agent Builder** features in Kibana require a matching Elastic Cloud / Serverless deployment
- **Kibana Workflows** require Kibana 8.14+ or Elastic Serverless
