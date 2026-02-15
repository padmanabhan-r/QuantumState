# Changelog

All notable changes to this project will be documented in this file.

## [0.1.0] - 2026-02-15

### Added
- **Agent Swarm System**: Implemented 3 specialized agents (Cassandra, Archaeologist, Surgeon) for autonomous SRE incident detection and remediation
- **Elasticsearch Integration**: ES|QL queries for anomaly detection with window functions for baseline comparison
- **Frontend UI**: React + Vite + TypeScript dashboard with landing page, console, and simulation control
- **Backend API**: FastAPI backend with endpoints for incidents, health, pipeline, chat, and simulation
- **Data Generation**: Synthetic data generators for metrics, logs, and incidents
- **Agent Orchestration**: Hand-off pattern where agents pass structured data through a chain

### Changed
- Refactored entire folder structure for better organization
- Consolidated documentation and simplified README

### Fixed
- Removed data-model.md reference from README

### Features
- Sim Control Feature for simulating live production environment
- Agent orchestration with web interface
- Auto mode for automated incident response
