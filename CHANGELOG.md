# Changelog

All notable changes to this project will be documented in this file.

---

## [0.3.0] - 2026-02-15

### The Real Infrastructure Release

v0.3.0 replaces synthetic remediation with real Docker container operations. The pipeline now detects actual memory leaks, triggers a real container restart via MCP runner, and verifies genuine recovery — nothing simulated.

### Added

**Real Docker Service Containers (`infra/services/`)**
- 4 FastAPI containers: payment-service, checkout-service, auth-service, inventory-service
- `/health` — reports memory as % of simulated 512MB container limit
- `/simulate/leak` — allocates real memory (4MB/5s), emits HEAP_PRESSURE/CONN_POOL_EXHAUSTED logs to ES
- `/simulate/spike` — bumps error_rate and latency, auto-resets after N seconds
- `/simulate/reset` — clears all fault state

**Metrics Scraper (`infra/scraper/`)**
- Polls `/health` on all 4 containers every 10s
- Writes real readings to `metrics-quantumstate` (same schema as synthetic)
- Falls back to synthetic values if a container is unreachable

**MCP Runner (`infra/mcp-runner/`)**
- Polls `remediation-actions-quantumstate` every 0.5s for `status: "pending"`
- Executes real `docker restart` via Python Docker SDK (socket mounted)
- Updates action status to `executed` and writes result to `remediation-results-quantumstate`

**Docker Compose (`infra/docker-compose.yml`)**
- All 7 containers wired: 4 services + Redis + scraper + MCP runner
- Docker socket mounted for runner

### Changed

- `detect_memory_leak` ES|QL query — replaced hardcoded 52% baseline with dynamic `MIN(value)` + absolute `> 60%` threshold
- `verify_resolution` and `get_recent_anomaly_metrics` — changed `request_latency_ms` → `latency_ms` to match scraper field name
- Guardian latency threshold raised to 400ms (aligned with query)

### Result

**MTTR 7m 53s on real infrastructure.** Memory leak injected → container restarted → Guardian RESOLVED.

---

## [0.2.0] - 2026-02-15

### The Closed Loop Release

v0.2.0 upgrades QuantumState from a 3-agent read-only advisory system into a fully closed-loop autonomous remediation platform. Agents now detect, investigate, execute, and verify — end to end, without human intervention.

### Added

**Guardian Agent (4th agent — Verification)**
- New Kibana Agent Builder agent `guardian-verification-agent` with 6-step verification protocol
- Runs post-remediation: retrieves action record, incident timestamp, current metrics, checks 3 recovery thresholds
- Returns `RESOLVED` or `ESCALATE` verdict with MTTR calculation
- Streams live reasoning to console terminal via SSE (`/api/guardian/stream/{service}`)
- Background worker polls `remediation-actions-quantumstate` every 60s for executed actions
- Updates incident doc with `guardian_verified: true`, `resolution_status`, `mttr_seconds`

**Autonomous Remediation Pipeline**
- Surgeon now outputs `recommended_action`, `confidence_score`, `risk_level` in structured format
- `_maybe_trigger_remediation()` — autonomously fires if confidence ≥ threshold (default 0.75)
- `AUTONOMOUS_MODE` and `REMEDIATION_CONFIDENCE_THRESHOLD` env var controls
- Recovery profiles: 8 metric recovery points per action type written to ES immediately after remediation

**Elastic Workflow — `QuantumState — Autonomous Remediation`**
- YAML Kibana Workflow (`elastic-setup/workflows/remediation-workflow.yaml`)
- Deploy script: `elastic-setup/workflows/deploy_workflow.py`
- On trigger: validates confidence, creates Kibana Case, writes audit to ES
- `REMEDIATION_WORKFLOW_ID` env var wired through backend

**New Backend Routes**
- `POST /api/remediate` — writes recovery metrics to ES, returns exec_id
- `GET /api/actions` — live remediation action feed for frontend
- `POST /api/workflow/trigger` — triggers Kibana Workflow
- `POST /api/guardian/stream/{service}` — SSE stream of Guardian agent reasoning

**New Frontend Components**
- `ActionsPanel.tsx` — live remediation action feed, polls `/api/actions` every 10s, colour-coded by action type and status
- `MttrStats.tsx` — MTTR reduction strip (manual baseline vs QuantumState average)
- Console right panel now tabbed: Incidents / Actions
- Guardian as 4th agent pill in console hero bar
- `PipelinePanel.tsx` — Guardian as 4th stage, new SSE event renderers: `remediation_triggered`, `remediation_executing`, `guardian_verdict`, `remediation_skipped`
- "Verify with Guardian" purple button appears after remediation fires
- Guardian running indicator with purple spinner

**New Elasticsearch Indices**
- `remediation-actions-quantumstate` — executed remediations with exec_id, risk level, workflow status
- `remediation-results-quantumstate` — Guardian verdict records
- `approval-requests-quantumstate` — human approval requests (ready for Tactician roadmap)

**New Tools (Kibana Agent Builder)**
- Tool 10: `get_incident_record` — retrieves latest incident for a service (for MTTR calculation)
- Tool 11: `get_remediation_action` — retrieves latest executed action for a service
- Tool 12: `quantumstate.autonomous_remediation` — Workflow tool wrapping the Kibana Workflow

**Documentation**
- `HOW_IT_WORKS.md` — plain-English explainer for non-SREs (what is real, what is simulated, how each agent works)
- `README.md` — full rewrite for v2 with 4-agent architecture, all indices, deploy steps
- `data-model.md` — updated with all 7 indices, complete field tables, recovery profiles
- `agents-definition.md` — Guardian agent definition with full system prompt, all 12 tools, colour codes

### Changed

- `ArchitectureSection.tsx` — Guardian moved to live agents, 2 new indices shown, 3-col grid
- `AgentPipeline.tsx` — Guardian live at index 3, divider between Guardian and Tactician
- `RoadmapSection.tsx` — Guardian removed, 2-col grid (Tactician + Diplomat only)
- `HeroSection.tsx` — "3 AI Agents" → "4 AI Agents"
- `MetricsBar.tsx` — live agents counter 3 → 4
- `HowItWorksSection.tsx` — Step 04 Guardian added, 4-col grid, updated subtitle
- `backend/main.py` — lifespan context manager, Guardian worker starts on startup
- `backend/routers/sim.py` — 3 new index mappings, all missing incident fields added, `guardian_verified` field, fixed `action_taken` field naming consistency

### Fixed

- `actions_taken` → `action_taken` field name consistency across seed data, mapping, and pipeline
- `incidents-quantumstate` mapping now includes all fields written by pipeline: `recommended_action`, `confidence_score`, `risk_level`, `pipeline_summary`, `guardian_verified`, `pipeline_run`
- `remediation-actions-quantumstate` mapping now includes `root_cause` field written by Guardian
- Guardian ES|QL Tool 10 `guardian_verified` field — was causing red squiggly (unmapped), now in index mapping

---

## [0.1.0] - 2026-01-28

### The Advisory Release

Initial release. Three-agent read-only advisory system.

### Added
- **Cassandra** (Detection) — ES|QL anomaly detection with window functions, time-to-failure estimation
- **Archaeologist** (Investigation) — log search, deployment correlation, historical incident matching
- **Surgeon** (Remediation) — action recommendation, metric sampling, resolution verification
- **Elastic Agent Builder** — all 3 agents as native Kibana agents with 9 custom ES|QL tools
- **FastAPI backend** — SSE streaming orchestration via `/api/agent_builder/converse/async`
- **React frontend** — landing page, SRE console, simulation control
- **Simulation Control** — setup, stream, inject, cleanup for all demo scenarios
- **3 demo scenarios** — memory leak, deployment regression, error spike
- **4 Elasticsearch indices** — metrics, logs, incidents, agent-decisions
