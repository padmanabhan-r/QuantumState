# Building a Self-Healing Incident Response System with Elasticsearch Agent Builder and Vector Search

**Author:** Padmanabhan Rajendrakumar, Technical Project Manager AI/ML
**Published:** February 18, 2026
[LinkedIn](https://www.linkedin.com/in/padmanabhan-rajendrakumar) · [GitHub](https://github.com/padmanabhan-r)

> This blog post was submitted to the Elastic Blog-a-thon Contest and is eligible to win a prize.

**Abstract:** Production systems need more than noisy alerts. This post walks through building a fully autonomous incident response system using Elastic's Agent Builder and ELSER vector search. By combining ES|QL reasoning, semantic search, and workflow execution, this setup drops Mean Time to Recovery from an hour down to under four minutes in our simulated environment.

---

## Introducing the Elastic Agent Builder

Setting up observability agents usually means wrestling with external orchestration tools, writing custom glue code, and managing multiple integrations. You end up moving data out of Elasticsearch, storing embeddings somewhere else, and triggering actions in yet another system. It adds latency, increases operational overhead, and makes the whole architecture fragile.

Elastic Agent Builder changes the game by letting you build agents right where your logs, metrics, and indices already live. You can tap into native tools like ES|QL and the built in Index Search tool, which handles vector search via ELSER. You do not need a separate vector database or an external retrieval pipeline.

You simply define your workflows and logic natively. Agents can query live data, pull semantic context across your indices, and kick off Elastic Workflows in one unified spot. Plus, it provides a clean UI and full Kibana API access for CI/CD automation.

<img src="../images/Elastic Agent Builder - Home.png" width="700" alt="Elastic Agent Builder - Home" />
<img src="../images/Elastic Agent Builder - New Agent.png" width="700" alt="Elastic Agent Builder - New Agent" />

[Official documentation](https://www.elastic.co/docs/explore-analyze/ai-features/agent-builder/agent-builder-agents)

---

## The Real Problem: Production Incidents and Manual Remediation

We have all been there. A backend service is humming along fine, but memory usage slowly creeps up. Eventually it crosses a critical threshold, latency spikes, and error rates climb. At 3:00 AM, the pager goes off.

An SRE wakes up and has to:
* Check dashboards
* Query logs
* Correlate recent deployments
* Guess the root cause
* Decide whether to restart, rollback, or scale
* Verify the system actually recovered

Even if your observability stack is perfect, MTTR stays high because a human still has to interpret the data and execute a fix. The real bottleneck is not detecting the problem; it is turning that detection into automated, reliable action.

---

## Introducing QuantumState

QuantumState is an autonomous incident response system I built on top of Elastic's Agent Builder. It uses four specialized AI agents to handle different phases of an incident lifecycle, and every query or decision happens right where the data sits.

The real magic happens in the vector search layer. Standard monitoring relies on rigid thresholds and exact keyword matches. QuantumState takes a smarter approach. It indexes both historical incidents and runbooks using ELSER sparse embeddings. This allows for hybrid search that combines BM25 lexical scoring with actual semantic relevance.

For example, if a current alert says "JVM heap climbing under load," the system can pull up a past incident labeled "GC pressure from retained connection pool objects." The wording is entirely different, but the root cause is the same. It applies the exact same logic to grab the right runbook procedure based on operational context, rather than relying on hardcoded mappings.

QuantumState takes an incident from detection all the way to verified recovery. The loop looks like this:

1. **Detect:** Catch metric anomalies before things break
2. **Investigate:** Correlate metrics, logs, and past incidents to find the root cause
3. **Execute:** Check the runbooks and trigger a fix when confidence is high
4. **Verify:** Make sure system health is back to normal

---

## The Agent Swarm

<img src="../images/Web - The 4 Agents.png" width="700" alt="Web - The 4 Agents" />

### 🔭 Cassandra: Detect

Cassandra monitors system metrics in real time. It uses dynamic baselines rather than static thresholds to catch patterns like memory leaks, latency drift, or error spikes early. When it spots an anomaly, Cassandra generates a structured context block describing the issue and its severity.

### 🔍 Archaeologist: Investigate

Archaeologist takes that anomaly and digs deeper. It correlates the metrics with logs and recent system activity to build a root cause hypothesis. It also runs a semantic search across historical incidents so the system can recognize similar failures regardless of the specific terminology used.

### ⚕️ Surgeon: Resolve

Surgeon figures out how to fix the problem. It retrieves the most relevant procedures from a semantically searchable runbook library. Once it is highly confident in a solution, Surgeon triggers a remediation workflow. This ensures the action is recorded safely. The action is written to Elasticsearch, where the MCP Runner picks it up to execute the actual infrastructure operation.

### 🛡️ Guardian: Verify

Guardian finishes the job. After the fix is applied, it checks if system health has returned to baseline. If the recovery conditions look good, the incident is resolved. If not, Guardian triggers escalation logic.

---

## The MCP Runner

The MCP Runner is the component that physically executes the fix. It continuously polls Elasticsearch for approved actions written by the agents and then performs the required operation. That could mean restarting a container, triggering a rollback, or scaling a dependency.

* No webhooks
* No external orchestration engines
* No separate automation platforms

Elasticsearch acts as the coordination layer and message bus. This keeps the architecture incredibly simple, auditable, and fully contained within the Elastic ecosystem.

---

## Architecture & Pipeline Flow

Here is how the data flows at a high level:

1. Metrics and logs stream continuously into Elasticsearch.
2. The Agent Pipeline orchestrates the four specialized agents.
3. When a fix is approved with a confidence score of 0.8 or higher, an Elastic Workflow triggers.
4. The Workflow records the action to maintain an audit trail.
5. The MCP Runner executes the infrastructure action.
6. The Guardian agent verifies recovery and closes the incident.

<img src="../images/architecture-flow.svg" width="700" alt="Architecture Flow" />

> Detection → Root Cause → Remediation → Verification → Closure

The result is a unified control plane where observability, decision making, and execution all operate within a single architecture.

---

## Implementation: Building QuantumState

QuantumState includes a React based SRE Incident Control Panel. It interacts directly with Agent Builder via the Kibana API to visualize agent reasoning and monitor outcomes in real time. We also have a separate local infrastructure stack that runs microservices, injects controlled faults, and generates live observability data for the agents to analyze.

The steps below walk through the full setup, from Elastic Cloud to a live remediation run.

The full source code is on GitHub: [github.com/padmanabhan-r/QuantumState](https://github.com/padmanabhan-r/QuantumState)

```bash
git clone https://github.com/padmanabhan-r/QuantumState.git
cd QuantumState
```

---

### Step 1: Elastic Cloud Setup

The easiest way to get started is with an [Elastic Cloud trial](https://cloud.elastic.co). It is free for 14 days and gives you a fully managed Elasticsearch and Kibana stack.

Once provisioned, create an API key from the Kibana UI. Copy your Elastic Cloud ID and the API key into your `.env` file. The Kibana URL is derived automatically from the Cloud ID, so you do not need to set it separately. You will add a third field (`REMEDIATION_WORKFLOW_ID`) after Step 4.

```env
ELASTIC_CLOUD_ID=My_Project:base64encodedstring==
ELASTIC_API_KEY=your_api_key_here==
```

Before running any setup scripts, enable both of these features in Kibana under **Advanced Settings**:

- `workflows:ui:enabled`
- `agentBuilder:experimentalFeatures`

---

### Step 2: The Indices

QuantumState uses seven specific indices:

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

QuantumState uses ELSER to power semantic search for the Archaeologist's historical incident lookup and the Surgeon's runbook retrieval.

```bash
python elastic-setup/setup_elser.py
```

This provisions the `.elser-2-elasticsearch` sparse embedding endpoint on your cluster. The script is idempotent; if ELSER is already deployed, it simply exits. You must do this before creating the agents because two of the 13 tools perform Index Search against ELSER indexed indices. Kibana validates that the underlying indices exist and are mapped correctly at tool creation time.

---

### Step 4: Deploy the Remediation Workflow

```bash
python elastic-setup/workflows/deploy_workflow.py
```

This script deploys `elastic-setup/workflows/remediation-workflow.yaml` to Kibana and prints the created workflow ID. Add that ID to your `.env` file. You can also just create the workflow manually in the Kibana UI by importing the yaml file.

```env
REMEDIATION_WORKFLOW_ID=workflow-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

---

### Step 5: Start the Application and Seed Baseline Data

```bash
./start.sh
```

Open `http://localhost:8080` and navigate to **Simulation & Setup → Run Setup**. This creates all seven Elasticsearch indices and seeds 100 historical incidents and 8 runbooks in a single pass. Both indices must exist before moving to the next step.

> In a real production environment, your incident history and runbook library would be orders of magnitude larger, giving ELSER significantly more signal to work with during semantic retrieval.

<img src="../images/Sim Control.png" width="700" alt="Simulation and Setup Control Panel" />

---

### Step 6: Create the Agents and Tools

```bash
python elastic-setup/setup_agents.py
```

This sets up all 13 tools and all 4 agents via the Kibana API in one run. Out of the 13 tools, 11 are ES|QL queries, 2 are semantic Index Search tools powered by ELSER, and 1 is the Workflow trigger. This script is also safe to re-run.

If you want to create the agents manually, you can find every agent ID, system prompt, tool assignment, and ES|QL query documented in `agents-definition.md`.

**Verify in Kibana:** Open Kibana → Agent Builder and confirm that all four agents appear with the correct tools assigned.

To tear everything down later, just run:

```bash
python elastic-setup/setup_agents.py --delete
```

<img src="../images/Elastic Agent Builder - Agents List.png" width="700" alt="Elastic Agent Builder - Agents List" />

---

### Step 7: Injecting Real Faults (Recommended)

This is where it gets fun.

The `infra/` directory contains a full local microservice environment wired together using Docker Compose. It includes four FastAPI services, a Redis dependency, a metrics scraper, and the MCP runner. By running this stack, the data Cassandra analyzes is entirely real. We are talking actual container memory allocation, real error logs, and an actual `docker restart` command to bring memory back down.

```bash
cd infra && docker compose up --build
```

Once running, the scraper writes live health readings to `metrics-quantumstate` every 15 seconds. You can inject a fault using the TUI control panel:

```bash
uv run python infra/control.py
```

The TUI shows live health for all four services. Press `1` to inject a memory leak into the payment-service, `2` for an error spike into the auth-service, or `0` to reset.

If you inject a memory leak, the payment-service starts allocating 4MB every 5 seconds in its Python heap. After about 30 seconds, the service emits realistic error logs. Surgeon will trigger remediation, the MCP runner will execute `docker restart payment-service`, and memory will drop back down. Finally, Guardian will verify the recovery using the post restart metrics.

**No Docker?** You can use the web console at `http://localhost:8080` → Simulation & Setup to inject simulated anomalies without running the containers.

---

### Step 8: Running the Pipeline

From the Console tab, click **Run Pipeline**. This kicks off the sequence: Cassandra → Archaeologist → Surgeon → Guardian. You can watch the agent reasoning stream live to the console.

My recommended sequence for testing:

1. Start the Docker stack
2. Wait 2 minutes for baseline metrics to gather
3. Inject a fault
4. Wait 60 to 90 seconds
5. Click Run Pipeline

<img src="../images/Console and TUI.png" width="700" alt="SRE Console and TUI Control Panel" />

---

## Demo UI

<img src="../images/TUI - Leak.png" width="700" alt="TUI showing active memory leak injection" />

<img src="../images/Pipeline Run - Resolved.png" width="700" alt="Pipeline run completing with Guardian RESOLVED verdict" />

<img src="../images/TUI - After Restart Healthy.png" width="700" alt="TUI showing service recovered after container restart" />

The pipeline runs end to end without human intervention:

- Real memory allocation
- Real semantic retrieval
- Real workflow trigger
- Real container restart
- Real recovery validation

For more details, check out the [website](https://www.quantumstate.online/) or explore the source code on [GitHub](https://github.com/padmanabhan-r/QuantumState).

---

## Conclusion and Takeaways

QuantumState demonstrates that a fully autonomous incident response system (detect, investigate, remediate, verify) can be built entirely within Elastic. No external LLM API keys. No separate vector database. No orchestration middleware.

Three capabilities make this possible: ES|QL for precise anomaly detection directly over live metrics; ELSER for semantic reasoning that matches meaning rather than keywords; and Agent Builder to coordinate the entire pipeline as native Kibana agents.

**Key takeaways:**

- ELSER hybrid search eliminates brittle keyword matching for both incident recall and runbook retrieval: "heap exhaustion" matches "GC pressure" without any custom synonym configuration
- Agent Builder removes the need for external frameworks; the entire pipeline lives inside Elastic
- Elasticsearch serves simultaneously as data store, knowledge base, action queue, and audit trail
- The full architecture is reproducible against any Elastic Cloud deployment

---

Disclaimer: This blog was submitted as part of the Elastic Blogathon.
