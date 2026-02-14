# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

QuantumState is an autonomous SRE agent swarm system that detects, investigates, and auto-remediates production incidents using Elasticsearch 8.x, ES|QL, and Python. The system consists of 6 specialized agents that work together to predict failures before they cascade.

## Development Commands

### Environment Setup
```bash
# Activate virtual environment
source .venv/bin/activate

# Install/update dependencies
pip install elasticsearch python-dotenv requests faker pandas numpy

# Configure Elastic credentials (create .env file)
# Required vars: ELASTIC_CLOUD_ID, ELASTIC_PASSWORD, ELASTIC_URL, KIBANA_URL
```

### Elastic Stack Operations
```bash
# Create index templates
python elastic-setup/templates/create_templates.py

# Generate synthetic data (metrics, logs, incidents)
python data/generators/generate_all.py
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

The system uses a **hand-off pattern** where agents pass structured data through a chain:

1. **Cassandra** (Detection) - Uses ES|QL to detect anomalies in metrics, predicts time-to-failure
2. **Archaeologist** (Investigation) - Searches logs/deployments, builds evidence chains, determines root cause
3. **Tactician** (Decision) - Evaluates remediation options, determines if approval needed
4. **Diplomat** (Liaison) - Manages human approvals and communications (optional gate)
5. **Surgeon** (Execution) - Executes Elastic Workflows with rollback safety
6. **Guardian** (Verification) - Validates outcomes, stores learnings

**Key Concept**: Each agent returns `{'next_agent': 'agent_name', 'data': {...}}` to hand off to the next agent. The orchestrator manages the flow.

### Agent Base Class

All agents inherit from `BaseAgent` (agents/base_agent.py) which provides:
- Elasticsearch connection management
- `log_decision()` - Records agent decisions to `agent-decisions-quantumstate` index
- `run_esql()` - Executes ES|QL queries
- `search()` - Executes standard Elasticsearch queries
- `process(input_data)` - Main processing method (must be overridden)

### Data Indices

The system uses three main index patterns:
- `metrics-quantumstate*` - Time-series metrics (CPU, memory, error rates)
- `logs-quantumstate*` - Application logs with severity levels
- `incidents-quantumstate*` - Historical incidents for learning
- `agent-decisions-quantumstate*` - Agent decision audit trail

## Key Patterns

### ES|QL for Anomaly Detection

ES|QL queries use window functions for baseline comparison:
```esql
| STATS
    current = AVG(value),
    baseline = AVG(value) OVER (ORDER BY @timestamp ROWS BETWEEN 20 PRECEDING AND 10 PRECEDING)
  BY service, region
| EVAL rate_per_min = (current - baseline) / 10
| WHERE rate_per_min > 1.5
```

This pattern appears throughout Cassandra's detection logic. The moving average baseline helps identify gradual degradation (like memory leaks) vs. spikes.

### Data Structure for Agent Communication

Agents pass enriched context as they process:
```python
{
    'anomaly_detected': True,
    'anomaly_type': 'memory_leak_progressive',
    'affected_services': ['payment-service'],
    'affected_regions': ['us-east-1'],
    'time_to_critical_seconds': 228,
    'confidence_score': 90,
    # Archaeologist adds:
    'root_cause_hypothesis': '...',
    'evidence_chain': [...],
    # Tactician adds:
    'selected_action': 'immediate_rollback',
    'approval_required': True
}
```

Each agent enriches this structure rather than replacing it.

### Synthetic Data Generation

Data generators in `data/generators/` create realistic patterns:
- **Normal metrics**: Baseline with natural variation
- **Anomaly injection**: Specific failure patterns (memory leaks, error spikes)
- **Temporal correlation**: Logs correspond to metric anomalies

When adding new anomaly types, inject both metrics AND corresponding logs to enable correlation.

### Environment Configuration

All Elastic connection logic reads from `.env`:
```python
from dotenv import load_dotenv
load_dotenv()

es = Elasticsearch(
    cloud_id=os.getenv('ELASTIC_CLOUD_ID'),
    basic_auth=('elastic', os.getenv('ELASTIC_PASSWORD'))
)
```

For local Docker deployments, use `ELASTIC_URL` instead of `CLOUD_ID`.

## Project Structure

```
quantumstate/
├── frontend/            # React + Vite + TypeScript UI
│   └── src/
│       ├── pages/       # Index, Console, SimControl
│       └── components/  # console/, landing/, ui/
├── backend/             # FastAPI Python backend
│   ├── main.py
│   ├── elastic.py       # Shared ES client
│   ├── inject.py        # Anomaly injection functions
│   ├── orchestrator.py  # Agent Builder converse_stream
│   └── routers/         # incidents, health, pipeline, chat, sim
├── start.sh             # Starts both frontend + backend
└── .env                 # Elastic credentials
```

## Testing Strategy

Current testing approach:
1. Generate synthetic data with known anomalies
2. Run individual agents with mock inputs
3. Verify agent output structure
4. Run full orchestrator to test end-to-end flow

When adding new agents, test in isolation first using the `if __name__ == '__main__'` pattern shown in existing agents.

## Common Scenarios

### Adding a New Agent

1. Inherit from `BaseAgent`
2. Implement `process(input_data)` method
3. Use `self.log_decision()` to record decisions
4. Return `{'next_agent': 'next', 'data': {...}}`
5. Add to orchestrator's agent registry
6. Add test section at bottom of file

### Creating New Anomaly Detection Queries

1. Test query in Kibana Dev Tools first
2. Save to `elastic-setup/queries/`
3. Add to Cassandra agent's detection methods
4. Update data generators to create test data
5. Define expected output structure

### Modifying Agent Communication Flow

The orchestrator manages linear flow. To add conditional branching:
- Agents return `next_agent` based on conditions (see Tactician)
- Example: `'next_agent': 'diplomat' if approval_required else 'surgeon'`

## Dependencies

Core dependencies (see pyproject.toml):
- `elasticsearch>=8.11.0` - ES client with ES|QL support
- `python-dotenv` - Environment variable management
- `faker`, `pandas`, `numpy` - Data generation

Requires Python 3.12+ (see .python-version).

## Elasticsearch Version Requirements

- ES 8.x required for ES|QL support
- Window functions (`OVER` clause) require ES 8.11+
- Agent Builder features in Kibana require matching version
