# Changelog

All notable changes to this project will be documented in this file.

---

## [0.4.0] - 2026-02-18

### ELSER Hybrid Search, Runbooks & Pipeline Hardening

v0.4.0 adds semantic search across historical incidents and runbooks via ELSER, hardens the detection and dedup logic, and eliminates race conditions in the pipeline.

### Added

- **ELSER hybrid search — Archaeologist** (`find_similar_incidents`) — Index Search tool over `incidents-quantumstate` using ELSER `semantic_text` embeddings; surfaces past incidents by meaning, not just keywords ("heap exhaustion" matches "GC pressure", "OOM kill")
- **ELSER hybrid search — Surgeon** (`find_relevant_runbook`) — Index Search tool over `runbooks-quantumstate`; Surgeon retrieves the most semantically relevant procedure before triggering remediation
- **`runbooks-quantumstate` index** — 8 runbooks covering memory leak, error spike, deployment regression, cache failure, and dependency restart scenarios; seeded via `python elastic-setup/seed_runbooks.py`
- **`setup_elser.py`** — one-shot script to deploy the `.elser-2-elasticsearch` inference endpoint; idempotent, exits immediately if already deployed
- **Pipeline race condition lock** — `threading.Lock` in `pipeline.py` prevents concurrent pipeline runs from both passing the dedup check before either writes a REMEDIATING incident, eliminating duplicate incidents and duplicate Kibana Cases

### Changed

- **Detection queries — 5-minute window** — `detect_memory_leak` and `detect_error_spike` now scan `NOW() - 5 minutes` using `MAX(value)` vs `AVG(value)`; eliminates AVG dilution that was delaying detection until near-saturation; catches leaks within ~3 minutes of injection
- **Dedup logic — status-driven** — replaced 30-minute time-based dedup with status-driven logic: `REMEDIATING < 15 min` blocks (in-flight); `RESOLVED < 3 min` blocks (ghost cooldown); everything else allows through immediately — consecutive real incidents on the same service are never suppressed
- **Surgeon — 1 Case per pipeline run** — Surgeon now remediates the single most critical service per run (highest confidence / most severe deviation); all other detected services are set to MONITORING and handled on the next run; eliminates Case spam when multiple anomalies coincide
- **Cassandra prompt** — updated detection threshold to match live query: 65% peak, 5-minute window (was 70%, 30 minutes)
- **Console — Chat panel removed** — "Chat with Agents" tab removed from SRE Console; use Kibana Agent Builder directly for per-agent chat
- **Architecture section** — all 7 indices displayed in a single row; agent name pills enlarged; connector label updated to `ES|QL · ELSER · Tool Calls`
- **Landing page** — ELSER hybrid search pill added to WhatIs section; Archaeologist and Surgeon step cards updated with ELSER tags; index counter updated to 7
- **TUI control panel** — fixed recovery log: `_last_status` is now preserved during container offline/restarting period so the `degraded → healthy` transition correctly fires in the log after MCP runner restarts a container

### Result

**Semantic search closes the knowledge gap.** Archaeologist now finds incidents by meaning rather than keyword match. Surgeon retrieves the exact runbook for the failure mode rather than relying on hardcoded action mappings. Detection is consistent from the first minutes of fault injection rather than only at near-saturation.

---

## [0.3.1] - 2026-02-15

### Demo Polish & Error Spike Support

End-to-end validation of the error spike scenario on real Docker infra. Guardian auto-triggers after remediation. Sim Control restructured for cleaner demo flow.

### Added

- **Guardian auto-countdown** — 90s countdown appears in console after Surgeon fires; Guardian triggers automatically without pressing "Verify with Guardian". "Verify now" button still available to skip the wait.
- **Guardian chat** — Guardian added to the "Talk to agent" selector in the console chat panel
- **`/api/cleanup/incidents`** endpoint — clears incident, remediation, and guardian result docs while keeping baseline metrics intact
- **Sim Control toggle** — Real Infra (Docker Sim) and Synthetic Sim now separated with a tab toggle; Real Infra is default. Docker inject cards include inline Reset buttons.
- **Cooldown bypass for ESCALATE** — pipeline re-runs are no longer blocked if the previous incident for that service ended with ESCALATE (unresolved)

### Changed

- **`verify_resolution` query** — window reduced from `NOW() - 10 minutes` to `NOW() - 1 minute` so Guardian only sees post-restart clean readings
- **Guardian system prompt Step 3** — updated to reference "last 1 minute" to match query
- **Guardian error_rate threshold** — raised from `< 2` to `< 2.5` errors/min to avoid false ESCALATEs from marginal post-recovery readings
- **Spike log templates** — changed from Redis-themed (`CACHE_MISS`, `REQUEST_TIMEOUT`) to deployment-regression themed (`UNHANDLED_EXCEPTION`, `REQUEST_FAILURE`) so Surgeon correctly selects `rollback_deployment` instead of `scale_cache`
- **MTTR strip** — "vs manual" label updated to "vs 47min manual avg" for transparency
- **Sim Control** — Deployment Rollback scenario removed; only Memory Leak and Error Spike remain (both proven end-to-end on real infra)

### Result

**Error spike proven on real infrastructure.** Unhandled exception injected → Cassandra detects error_rate 2400% above baseline → Archaeologist finds deployment regression logs → Surgeon fires `rollback_deployment` (confidence 0.95) → MCP runner executes `docker stop+start checkout-service` → Guardian auto-triggers at T+90s → **RESOLVED**.

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

- `detect_memory_leak` ES|QL query — split into a 5-min recent window (`MAX`) vs 5–20 min baseline (`AVG`); eliminates signal dilution from averaging the full window; detects within minutes of leak start instead of only at saturation
- `detect_error_spike` ES|QL query — same split-window fix: `MAX` of last 3 minutes vs full-window `AVG`; catches spikes immediately rather than after the average crosses threshold
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
