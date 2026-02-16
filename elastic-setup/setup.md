# QuantumState — Agent Setup

## Before you begin

1. **Create an Elastic Cloud trial** at [cloud.elastic.co](https://cloud.elastic.co) and spin up a new serverless Elasticsearch project (or a hosted deployment on 9.2+).

2. **Enable Workflows** — in your deployment go to Kibana → Stack Management → Advanced Settings, search for `workflows` and enable both `workflows:ui:enabled` and `workflows:api:enabled`.

3. **Enable Agent Builder** — in the same Advanced Settings page, search for `agentBuilder` and enable `agentBuilder:enabled`.

---

## Setup order

> The workflow must exist before the agents are created — the Surgeon agent requires its ID.
> Follow the steps below in order.

### Step 1 — Add credentials to `.env`

```
ELASTIC_API_KEY=<API key with agentBuilder Kibana privileges>
KIBANA_URL=https://xxx.kb.us-east-1.aws.elastic.cloud
```

Use an API key with the `agentBuilder` Kibana feature privilege and `monitor_inference` Elasticsearch cluster privilege. You can also set `ELASTIC_CLOUD_ID` instead of `KIBANA_URL` and the scripts will derive it automatically.

### Step 2 — Deploy the remediation workflow

```bash
python elastic-setup/workflows/deploy_workflow.py
```

The script prints the created workflow ID. Add it to `.env`:

```
REMEDIATION_WORKFLOW_ID=<id printed above>
```

### Step 3 — Run agent setup

```bash
python elastic-setup/setup_agents.py
```

This creates (or updates if they already exist):

| What | Count |
|------|-------|
| ES\|QL tools | 11 |
| Workflow tool (Guardian only) | 1 |
| Agents | 4 |

**Agents created:**
- `cassandra-detection-agent` — detects memory leaks and error spikes
- `archaeologist-investigation-agent` — correlates logs, deployments, history
- `surgeon-action-agent` — assesses state, selects action, produces incident report
- `guardian-verification-agent` — verifies remediation success, can re-trigger workflow

The script is idempotent — safe to re-run to update instructions or tools.

---

## Teardown

```bash
python elastic-setup/setup_agents.py --delete
```

Deletes all 4 agents and all 12 tools.
