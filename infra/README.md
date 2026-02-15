# QuantumState — infra/

Phase 3 real infrastructure. Four microservice containers, a metrics scraper, and an MCP runner that executes real Docker operations when the pipeline fires.

## Structure

```
infra/
├── services/
│   ├── base/               Single FastAPI app — all 4 services use this image
│   │   ├── main.py         /health, /simulate/leak, /simulate/spike, /simulate/reset
│   │   ├── requirements.txt
│   │   └── Dockerfile
│   ├── payment-service/    .env (SERVICE_NAME + PORT overrides)
│   ├── checkout-service/
│   ├── auth-service/
│   └── inventory-service/
├── scraper/
│   ├── scraper.py          Polls /health every 15s → writes to metrics-quantumstate
│   ├── requirements.txt
│   └── Dockerfile
├── mcp-runner/
│   ├── runner.py           Polls ES every 0.5s → docker-mcp → real restart
│   ├── mcp_config.json
│   ├── requirements.txt
│   └── Dockerfile
└── docker-compose.yml      Wires everything together
```

## Quick start

```bash
cd infra
docker compose up --build
```

Services available at:
| Container | Port | Health |
|---|---|---|
| payment-service | 8001 | http://localhost:8001/health |
| checkout-service | 8002 | http://localhost:8002/health |
| auth-service | 8003 | http://localhost:8003/health |
| inventory-service | 8004 | http://localhost:8004/health |
| auth-redis | 6379 | — |

## Fault injection

```bash
# Inject real memory leak into payment-service
curl -X POST http://localhost:8001/simulate/leak

# Inject error spike into auth-service for 120s
curl -X POST http://localhost:8003/simulate/spike

# Reset all faults
curl -X POST http://localhost:8001/simulate/reset
```

## How it connects to the pipeline

1. Scraper writes real `/health` readings to `metrics-quantumstate` every 15s
2. Cassandra detects anomaly from real data (not synthetic)
3. Surgeon writes action to `remediation-actions-quantumstate` with `status: executing`
4. MCP runner picks it up within 0.5s, calls `docker restart payment-service`
5. Container restarts (2–5s gap), memory drops for real
6. Scraper picks up recovered stats, writes to ES
7. Guardian reads real recovery curve → RESOLVED

## MCP Runner

The runner uses `uvx docker-mcp` to execute Docker operations. It requires the Docker socket mounted:
```yaml
volumes:
  - /var/run/docker.sock:/var/run/docker.sock
```

If `docker-mcp` fails, it falls back to `POST /api/remediate` (synthetic recovery) so the pipeline never stalls.

## Env vars required (from root .env)

```
ELASTIC_CLOUD_ID=...
ELASTIC_API_KEY=...
```
