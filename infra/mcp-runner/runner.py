"""
QuantumState — MCP Runner
Polls remediation-actions-quantumstate every 0.5s for status="executing".
Routes to docker-mcp to perform real container operations.
Falls back to synthetic recovery endpoint if Docker call fails.
"""
import os
import time
import datetime as dt
import requests
import docker as docker_sdk
from elasticsearch import Elasticsearch, ConflictError
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

# --- Clients ---
es = Elasticsearch(
    cloud_id=os.getenv("ELASTIC_CLOUD_ID"),
    api_key=os.getenv("ELASTIC_API_KEY"),
)

POLL_INTERVAL      = float(os.getenv("POLL_INTERVAL_SECONDS", "0.5"))
ACTIONS_INDEX      = "remediation-actions-quantumstate"
RESULTS_INDEX      = "remediation-results-quantumstate"
FALLBACK_URL       = os.getenv("BACKEND_URL", "http://localhost:8000") + "/api/remediate"

# Container name mapping: service field → Docker container name
CONTAINER_MAP = {
    "payment-service":   "payment-service",
    "checkout-service":  "checkout-service",
    "auth-service":      "auth-service",
    "inventory-service": "inventory-service",
}

REDIS_CONTAINER = "auth-redis"

# Docker SDK client (uses mounted /var/run/docker.sock)
_docker_client = docker_sdk.from_env()


def execute_action(action_doc: dict) -> dict:
    action    = action_doc.get("action")
    service   = action_doc.get("service", "")
    container = CONTAINER_MAP.get(service, service)

    print(f"[runner] Executing {action} on {container}")

    try:
        c = _docker_client.containers.get(container)

        if action == "restart_service":
            c.restart()
            return {"ok": True, "output": f"restarted {container}"}

        elif action == "rollback_deployment":
            c.stop()
            c.start()
            return {"ok": True, "output": f"stop+start {container}"}

        elif action == "scale_cache":
            _docker_client.containers.run(
                "redis:7-alpine",
                name=f"{container}-cache-{int(time.time())}",
                detach=True,
            )
            return {"ok": True, "output": "redis cache scaled"}

        elif action == "restart_dependency":
            dep = _docker_client.containers.get(REDIS_CONTAINER)
            dep.restart()
            return {"ok": True, "output": f"restarted {REDIS_CONTAINER}"}

        else:
            return {"ok": False, "output": f"Unknown action: {action}"}

    except Exception as e:
        return {"ok": False, "output": str(e)}


def fallback_remediate(action_doc: dict) -> dict:
    """Call the synthetic recovery endpoint if Docker execution fails."""
    try:
        resp = requests.post(FALLBACK_URL, json=action_doc, timeout=20)
        return {"ok": resp.ok, "output": "synthetic_fallback", "data": resp.json() if resp.ok else {}}
    except Exception as e:
        return {"ok": False, "output": f"fallback failed: {e}"}


def poll():
    """Fetch one pending 'executing' action from ES."""
    resp = es.search(
        index=ACTIONS_INDEX,
        body={
            "seq_no_primary_term": True,
            "query": {"term": {"status": "pending"}},
            "sort":  [{"@timestamp": "asc"}],
            "size":  1,
        },
    )
    hits = resp["hits"]["hits"]
    return hits[0] if hits else None


def lock_and_process(hit: dict):
    doc_id  = hit["_id"]
    seq_no  = hit["_seq_no"]
    pri_trm = hit["_primary_term"]
    doc     = hit["_source"]

    # Optimistic lock — mark as "running" to prevent double-execution
    try:
        es.update(
            index=ACTIONS_INDEX,
            id=doc_id,
            if_seq_no=seq_no,
            if_primary_term=pri_trm,
            body={"doc": {"status": "executing", "runner_started_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")}},
        )
    except ConflictError:
        print(f"[runner] {doc_id} already locked by another runner — skipping")
        return

    # Execute
    result = execute_action(doc)

    if not result["ok"]:
        print(f"[runner] Docker failed ({result['output']}) — trying fallback")
        result = fallback_remediate(doc)

    ts = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    final_status = "executed" if result["ok"] else "failed"

    # Update action doc
    es.update(
        index=ACTIONS_INDEX,
        id=doc_id,
        body={"doc": {
            "status":      final_status,
            "executed_at": ts,
            "runner_output": result.get("output", ""),
        }},
    )

    # Write result record
    es.index(
        index=RESULTS_INDEX,
        document={
            "@timestamp":     ts,
            "exec_id":        doc.get("exec_id"),
            "incident_id":    doc.get("incident_id"),
            "service":        doc.get("service"),
            "action":         doc.get("action"),
            "status":         final_status,
            "runner_output":  result.get("output", ""),
            "docker_used":    result.get("output") != "synthetic_fallback",
        },
    )

    print(f"[runner] {doc.get('service')} {doc.get('action')} → {final_status} | {result.get('output', '')[:80]}")


def run():
    print(f"[runner] Starting — poll_interval={POLL_INTERVAL}s")
    while True:
        try:
            hit = poll()
            if hit:
                lock_and_process(hit)
        except Exception as e:
            print(f"[runner] Error: {e}")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    run()
