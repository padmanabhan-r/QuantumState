# Building a Self-Healing Incident Response System with Elasticsearch Agent Builder and Vector Search

**Author:** Padmanabhan Rajendrakumar - Technical Project Manager AI/ML  
[LinkedIn](https://www.linkedin.com/in/padmanabhan-rajendrakumar) · [GitHub](https://github.com/padmanabhan-r)

**Abstract:** Modern production systems demand more than alerts. This article shows how Elastic's Agent Builder and native vector search powered by ELSER enable a fully autonomous self-healing incident response system built entirely within Elastic. By combining ES|QL reasoning, semantic search, and workflow-driven execution, the system cuts Mean Time to Recovery from nearly an hour to under four minutes in a simulated production environment.

---

## Introducing the Elastic Agent Builder

Building intelligent agents for observability traditionally requires external orchestration frameworks, custom glue code, and multiple integrations. Data must leave Elasticsearch, embeddings are stored in separate systems, and actions are triggered elsewhere. This increases latency, adds operational complexity, and creates fragile architectures, especially in high-volume SRE environments.

Elastic Agent Builder simplifies this.

It allows you to build agents directly inside Kibana, where your logs, metrics, and indices already live. Agents can use native tools such as ES|QL queries and the built-in Index Search tool, which supports seamless vector search over semantic fields powered by ELSER. There is no need for a separate vector database, external retrieval pipeline, or additional orchestration layer.

Instead of stitching systems together, you define tools, workflows, and reasoning logic natively within Elastic. Agents query live data, perform semantic retrieval across indices, and trigger Elastic Workflows in a single, unified environment. Agent Builder provides a clean UI for designing and managing agents, and it can also be accessed programmatically using the Kibana API for automation and CI/CD integration.

<img src="../images/Elastic Agent Builder - Home.png" width="700" alt="Elastic Agent Builder - Home" />

<img src="../images/Elastic Agent Builder - New Agent.png" width="700" alt="Elastic Agent Builder - New Agent" />

[Official documentation](https://www.elastic.co/docs/explore-analyze/ai-features/agent-builder/agent-builder-agents)

In the next section, we apply these capabilities to a challenging real-world SRE scenario and build a fully autonomous, closed-loop remediation system.

---

## The Real Problem: Production Incidents and Manual Remediation

Imagine a backend service running in production. Over time, memory usage starts increasing. At first, it looks harmless. Then it crosses a threshold. Latency begins to spike. Error rates rise. Alerts start firing. At 3:00 AM, someone gets called.

An SRE now has to:

- Check dashboards  
- Query logs  
- Correlate recent deployments  
- Identify the root cause  
- Decide on remediation (restart? rollback? scale?)  
- Verify that the system has recovered  

Even with good observability, this process is manual, repetitive, and time-sensitive. Mean Time To Recovery (MTTR) increases not because data is unavailable, but because humans must interpret and act on it.

The real problem is not detection. The real problem is turning detection into reliable, automated action.

---

## Introducing QuantumState

QuantumState is a self-healing incident response system that uses Elastic's Agent Builder to define, deploy, and orchestrate four specialized AI agents, each responsible for a distinct phase of the incident lifecycle, with every tool, query, and decision executed where the data already resides.

What makes this architecture possible is what Agent Builder provides out of the box. Each agent is assigned a precise set of tools: ES|QL queries for anomaly detection, log correlation, and metric verification, along with native vector search for knowledge retrieval powered by ELSER, Elastic’s Learned Sparse Encoder. There are no external LLM API keys and no orchestration middleware. The agents reason directly over live Elasticsearch indices and act on what they find.

The vector search layer is where the system becomes genuinely intelligent. Traditional monitoring depends on exact keyword matches or rigid thresholds. If the alert condition is not explicitly defined, the signal is missed. QuantumState takes a different approach. Both the historical incident library and the runbook collection are indexed using ELSER sparse embeddings, enabling hybrid search that combines BM25 lexical scoring with semantic relevance. When a current event describes "JVM heap climbing under load," the system runs a semantic search against historical incidents and retrieves a record described as "GC pressure from retained connection pool objects." Different wording, same root cause. For remediation, it performs the same semantic retrieval across the runbook library, selecting the most contextually relevant procedure instead of relying on hardcoded mappings. This is the difference between a rule engine and a system that understands operational context.

Together, the four agents form a closed-loop remediation pipeline:

1. **Detect** - Identify anomalies in metrics before they cascade  
2. **Investigate** - Correlate metrics, logs, and historical incidents to determine the root cause  
3. **Execute** - Consult the runbook library, then trigger a remediation action when confidence is high  
4. **Verify** - Confirm that system metrics have returned to baseline  

Instead of stopping at alerting, QuantumState carries the incident from detection to verified recovery automatically and auditably within Elastic.

---

## The Agent Swarm

QuantumState operates as a coordinated swarm of four specialized agents. Each agent is responsible for a specific stage of the incident lifecycle, together forming a fully closed-loop autonomous system.

### 🔭 Cassandra - Detect

Cassandra monitors system metrics in real time and identifies anomalies using dynamic baselines instead of static thresholds. It detects patterns such as memory leaks, latency drift, or error spikes before they escalate into critical failures. When an anomaly is found, Cassandra generates structured context describing the issue and its severity.

### 🔍 Archaeologist - Investigate

Archaeologist analyzes the anomaly in context. It correlates metrics with logs and recent system activity to construct a root cause hypothesis. It also performs semantic search across historical incidents, allowing the system to recognize similar failures even when terminology differs. This enables deeper contextual reasoning rather than simple keyword matching.

### ⚕️ Surgeon - Resolve

Surgeon determines the most appropriate remediation strategy. Instead of relying on hardcoded mappings, it retrieves relevant procedures from a semantically searchable runbook library. Once confidence is high, it triggers a remediation workflow, ensuring the action is recorded and executed in a controlled, auditable manner.

### 🛡️ Guardian - Verify

Guardian closes the loop. After remediation, it validates whether system health has returned to baseline. If recovery conditions are met, the incident is resolved. If not, escalation logic is triggered.

Together, these four agents transform observability data into verified action, carrying an incident from detection to confirmed recovery without human intervention.

<img src="../images/Web - The 4 Agents.png" width="700" alt="Web - The 4 Agents" />

---

## 🐳 The MCP Runner

The MCP Runner is the component that physically executes remediation. It acts as a lightweight sidecar that continuously polls for approved remediation actions written by the agents to Elasticsearch.

When an action is marked ready for execution, the MCP Runner performs the required infrastructure operation such as restarting a container or triggering a rollback.

- No webhooks  
- No external orchestration engines  
- No separate automation platform  

Elasticsearch acts as the coordination layer and message bus, while the MCP Runner bridges decision-making with real-world execution. This keeps the architecture simple, auditable, and fully controlled within the Elastic ecosystem.

---

## Architecture & Pipeline Flow

At a high level, the flow looks like this:

1. Metrics and logs stream continuously into Elasticsearch  
2. The Agent Pipeline orchestrates the four specialized agents  
3. When remediation is approved (confidence ≥ 0.8), an Elastic Workflow is triggered  
4. The Workflow records the action and maintains an auditable trail  
5. The MCP Runner executes the infrastructure action  
6. The Guardian agent verifies recovery and closes the incident  

This creates a fully autonomous loop:

> Detection → Root Cause → Remediation → Verification → Closure

The result is a unified control plane where observability, decision-making, and execution operate within a single, coherent architecture.

<img src="../images/architecture-flow.svg" width="700" alt="Architecture Flow" />

---

## Implementation: Building QuantumState

This section walks through the full implementation of QuantumState, from provisioning Elastic Cloud to deploying agents and triggering the live remediation pipeline.

To make the system fully interactive, QuantumState includes a React-based SRE Incident Control Panel that directly interacts with Agent Builder using the Kibana API. The console visualizes agent reasoning, triggers pipeline execution, and monitors remediation outcomes in real time. A separate local infrastructure stack runs microservices, injects controlled faults, and generates live observability data for the agents to analyze.

The following steps detail how to provision Elastic Cloud, deploy ELSER, configure agents and workflows, start the infrastructure stack, and execute the autonomous remediation loop.

---

### Step 1: Elastic Cloud Setup

The easiest way to get started is with an [Elastic Cloud trial](https://cloud.elastic.co). It's free for 14 days and provides a fully managed Elasticsearch and Kibana stack with no infrastructure to manage.

Once your deployment is provisioned, create an API key from the Kibana UI. Copy your Elastic Cloud ID and the API key into your `.env` file.

Create a `.env` file in the project root with two fields to start:

```env
ELASTIC_CLOUD_ID=My_Project:base64encodedstring==
ELASTIC_API_KEY=your_api_key_here==
```

The Kibana URL is derived automatically from the Cloud ID, so you do not need to set it separately. You will add a third field (`REMEDIATION_WORKFLOW_ID`) after Step 4.

**Enable Workflows and Agent Builder**

Before running any setup scripts, enable both features in Kibana.

Go to **Advanced Settings**, then enable:

- `workflows:ui:enabled`  
- `agentBuilder:experimentalFeatures`  

This is a one-time step. Without it, the workflow deployment and agent setup will fail.

---

### Step 2: The Indices

QuantumState uses seven indices:

| Index | Purpose |
|---|---|
| `metrics-quantumstate` | Time-series CPU, memory, error rate, latency |
| `logs-quantumstate` | Application logs and deployment events |
| `incidents-quantumstate` | Full incident lifecycle records with ELSER semantic field |
| `agent-decisions-quantumstate` | Agent decision audit trail |
| `remediation-actions-quantumstate` | Action queue polled by the MCP Runner |
| `remediation-results-quantumstate` | Guardian verdicts and post-fix metrics |
| `runbooks-quantumstate` | Semantically searchable remediation procedure library |

---

### Step 3: Deploy ELSER

QuantumState uses ELSER (Elastic Learned Sparse Encoder) to power semantic search in two places: the Archaeologist's historical incident lookup and the Surgeon's runbook retrieval.

Deploy the inference endpoint once before creating agents:

```bash
python elastic-setup/setup_elser.py
```

This provisions the `.elser-2-elasticsearch` sparse embedding endpoint on your cluster. The script is idempotent. If ELSER is already deployed, it exits immediately.

This step must come before agent creation because two of the 13 tools perform Index Search against ELSER-indexed indices, and Kibana validates at tool creation time that the underlying indices exist and are properly mapped.

---

### Step 4: Deploy the Remediation Workflow

The workflow must exist before agents are created because the Surgeon agent requires its ID.

```bash
python elastic-setup/workflows/deploy_workflow.py
```

The script deploys `elastic-setup/workflows/remediation-workflow.yaml` to Kibana and prints the created workflow ID. Add it to `.env`:

```env
REMEDIATION_WORKFLOW_ID=workflow-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

Alternatively, you can create the workflow manually in the Kibana UI by importing `elastic-setup/workflows/remediation-workflow.yaml`.

---

### Step 5: Start the Application and Seed Baseline Data

```bash
./start.sh
```

Once running, open `http://localhost:8080` and navigate to **Simulation & Setup → Run Setup**. This creates all seven Elasticsearch indices and seeds 100 historical incidents and 8 runbooks in a single pass. A live production system would contain significantly more data.

These datasets power the semantic search used by Archaeologist and Surgeon agents during pipeline execution. Both indices must exist before the next step, as Kibana validates them at tool creation time.

---

### Step 6: Create the Agents and Tools

With the workflow ID in `.env` and all indices populated, run the one-shot setup script:

```bash
python elastic-setup/setup_agents.py
```

This creates all 13 tools and all 4 agents via the Kibana API in a single run. The script is idempotent and safe to re-run if you update instructions or tools.

Of the 13 tools:
- 11 are ES|QL queries  
- 2 are semantic Index Search tools powered by ELSER  
- 1 is the Workflow trigger  

If you prefer to create agents manually in the Kibana UI, every agent ID, system prompt, tool assignment, and ES|QL query is documented in [`agents-definition.md`](https://github.com/padmanabhan-r/QuantumState/blob/main/agents-definition.md).

> **Verify in Kibana after setup.** Once the script completes, open Kibana → Agent Builder and confirm that all four agents appear with the correct tools assigned. Use `agents-definition.md` as the reference. If anything looks incorrect, edit it directly in the Kibana UI rather than re-running the script.

To tear everything down:

```bash
python elastic-setup/setup_agents.py --delete
```

<img src="../images/Elastic Agent Builder - Agents List.png" width="700" alt="Elastic Agent Builder - Agents List" />

---

### Step 7: Injecting Real Faults (Recommended)

This is where it gets interesting.

The `infra/` directory contains a complete local microservice environment: four FastAPI services, a Redis dependency, a metrics scraper, and the MCP runner, all wired together using Docker Compose.

Running this stack means the data Cassandra agent analyzes is real: actual memory allocation inside a container, actual error logs, and an actual `docker restart` bringing memory back down. Ensure you have Docker installed and running.

#### Start the stack

```bash
cd infra
docker compose up --build
```

This starts:

| Container | Port | Purpose |
|---|---|---|
| `payment-service` | 8001 | FastAPI service, memory leak target |
| `checkout-service` | 8002 | FastAPI service |
| `auth-service` | 8003 | FastAPI service, error spike target |
| `inventory-service` | 8004 | FastAPI service |
| `auth-redis` | 6379 | Redis dependency |
| `qs-scraper` | - | Polls `/health` every 15s and writes to `metrics-quantumstate` |
| `qs-mcp-runner` | - | Polls `remediation-actions-quantumstate` every 0.5s and runs `docker restart` |

Once running, the scraper immediately writes live readings to `metrics-quantumstate`. Cassandra now has real telemetry to analyze.

---

### Inject a Fault

The recommended interface is the TUI control panel:

```bash
uv run python infra/control.py
```

The TUI shows live health for all four services including memory, CPU, error rate, and latency, updating every 3 seconds.

- Press `1` to inject a memory leak into `payment-service`  
- Press `2` to inject an error spike into `auth-service`  
- Press `0` to reset everything  

You can also use curl:

```bash
curl -X POST http://localhost:8001/simulate/leak
curl -X POST http://localhost:8003/simulate/spike?duration=600
curl -X POST http://localhost:8001/simulate/reset
```

---

### What Actually Happens

Injecting a memory leak causes `payment-service` to allocate 4MB every 5 seconds in Python heap. This is real memory consumption.

The scraper captures these readings and writes them to `metrics-quantumstate`. After roughly 30 seconds, the service emits realistic error logs to `logs-quantumstate`.

Surgeon triggers remediation, and the MCP runner executes `docker restart payment-service`. The container restarts in 2 to 5 seconds. Memory drops back to baseline. Guardian agent verifies recovery using real post-restart metrics.

The entire loop, detection, restart, and recovery, is observable in real infrastructure.

> **No Docker?** The synthetic mode still works. Use the web console at `http://localhost:8080` → Sim Control to inject anomalies without running containers.

---

### Step 8: Running the Pipeline

QuantumState supports two modes: **Auto** and **Manual**.

#### Manual Pipeline Trigger

From the **Console** tab, click **Run Pipeline**. This invokes Cassandra → Archaeologist → Surgeon → Guardian. Agent reasoning streams live to the console.

Recommended sequence:

1. Start Docker stack  
2. Wait 2 minutes for baseline metrics  
3. Inject fault  
4. Wait 60 to 90 seconds  
5. Click Run Pipeline  

#### Auto Mode

An automated polling mode can be configured for production systems, but for this demo the pipeline is triggered manually to observe each agent’s reasoning step by step.

---

### Demo

The full pipeline runs end-to-end with no human intervention.

- Real memory allocation  
- Real semantic retrieval  
- Real workflow trigger  
- Real container restart  
- Real recovery validation  

For more details, visit the [live demo](https://www.quantumstate.online/) or explore the full source on [GitHub](https://github.com/padmanabhan-r/QuantumState).

Disclaimer: This blog was submitted as part of the Elastic Blogathon.