# Contributing to QuantumState

Thanks for your interest in contributing. This document covers how to get set up, what areas are open for contribution, and how to submit changes.

---

## Getting Started

### Prerequisites

- Python 3.12+
- Node.js 18+
- An Elastic Cloud deployment (ES 8.11+ with Kibana)
- [uv](https://github.com/astral-sh/uv) for Python dependency management

### Setup

```bash
# Clone the repo
git clone https://github.com/padmanabhan-rajendrakumar/quantumstate.git
cd quantumstate

# Install Python dependencies
uv sync

# Install frontend dependencies
cd frontend && npm install && cd ..

# Configure credentials
cp .env.example .env
# Edit .env with your ELASTIC_CLOUD_ID, ELASTIC_API_KEY, and REMEDIATION_WORKFLOW_ID
```

### One-time Elastic Setup

Run these in order before starting the app:

```bash
python elastic-setup/setup_elser.py          # Deploy ELSER inference endpoint
python elastic-setup/workflows/deploy_workflow.py  # Deploy remediation workflow
python elastic-setup/setup_agents.py         # Provision tools and agents
python elastic-setup/seed_runbooks.py        # Seed runbooks index
```

Then start the app:

```bash
./start.sh
```

Open `http://localhost:8080`, go to **Simulation & Setup → Run Setup** to create all indices and seed historical data.

---

## Areas for Contribution

### New Anomaly Scenarios

Add a new fault injection type:

1. Write the injection function in `backend/inject.py` — inject both metrics and logs
2. Register the scenario in `backend/routers/sim.py`
3. Use `latency_ms` (not `request_latency_ms`) for latency fields to match scraper schema

### New Runbooks

Add runbooks to `elastic-setup/seed_runbooks.py`. Each runbook needs a `runbook_text` field (used for ELSER semantic search by Surgeon) and a structured `steps` list.

### New ES|QL Detection Tools

1. Test the query in Kibana Dev Tools
2. Add the tool definition to `TOOLS` in `elastic-setup/setup_agents.py`
3. Update the relevant agent's system prompt in the same file
4. Re-run `python elastic-setup/setup_agents.py` — it patches existing tools and creates new ones

### Frontend

The UI is React + Vite + TypeScript. Pages live in `frontend/src/pages/`, components in `frontend/src/components/`. Run `npm run dev` from `frontend/` for hot-reload development.

---

## Submitting Changes

1. Fork the repo and create a branch from `main`
2. Make your changes — keep commits focused and atomic
3. Open a pull request with a clear description of what changed and why

### Commit Style

- Use the imperative mood: `add memory leak runbook`, not `added memory leak runbook`
- Reference the relevant component in the subject: `pipeline:`, `inject:`, `setup:`, etc.
- Keep the subject line under 72 characters

---

## Code Style

- **Python**: follow existing patterns — no type annotation additions to untouched code, no unnecessary abstractions
- **TypeScript**: match the existing component structure; no new dependencies without discussion
- **ES|QL**: test queries in Kibana Dev Tools before committing; use `MAX(value)` over `AVG` for detection queries to avoid signal dilution

---

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
