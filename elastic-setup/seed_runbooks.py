"""
QuantumState — Runbook Seeder

Creates the runbooks-quantumstate index with ELSER semantic_text fields
and seeds it with 8 runbooks covering all known incident patterns.

The Surgeon agent calls find_relevant_runbook (index_search tool) to retrieve
the most appropriate procedure before executing remediation.

Usage:
    python elastic-setup/seed_runbooks.py
    python elastic-setup/seed_runbooks.py --delete

Requirements:
    ELSER must be deployed first:
        python elastic-setup/setup_elser.py
"""

import os
import sys
import argparse
from pathlib import Path
from dotenv import load_dotenv
from elasticsearch import Elasticsearch

load_dotenv(Path(__file__).parent.parent / ".env")

ELASTIC_API_KEY  = os.getenv("ELASTIC_API_KEY", "")
ELASTIC_CLOUD_ID = os.getenv("ELASTIC_CLOUD_ID", "")
ELASTIC_URL      = os.getenv("ELASTIC_URL", "").rstrip("/")
INDEX            = "runbooks-quantumstate"
ELSER_ID         = ".elser-2-elasticsearch"

INDEX_BODY = {
    "mappings": {
        "properties": {
            "runbook_id":              {"type": "keyword"},
            "title":                   {"type": "text"},
            "service":                 {"type": "keyword"},   # specific service or "any"
            "action_type":             {"type": "keyword"},   # rollback_deployment | restart_service | scale_cache | restart_dependency
            "risk_level":              {"type": "keyword"},   # low | medium | high
            "estimated_time_minutes":  {"type": "integer"},
            "steps":                   {"type": "text"},
            # semantic_text — ELSER embeds this for hybrid search
            "runbook_text": {
                "type":         "semantic_text",
                "inference_id": ELSER_ID,
            },
        }
    }
}

# ── Runbook definitions ────────────────────────────────────────────────────────
# runbook_text is written the way a senior SRE would describe the situation:
# symptoms, context, contraindications, and steps in natural language.
# ELSER embeds this — so "heap growing" matches "memory leak" matches "OOM kill".

RUNBOOKS = [
    {
        "runbook_id": "rb-001",
        "title": "Payment service memory leak — rollback after recent deployment",
        "service": "payment-service",
        "action_type": "rollback_deployment",
        "risk_level": "medium",
        "estimated_time_minutes": 3,
        "steps": (
            "1. Confirm deployment timestamp (should be within last 90 min).\n"
            "2. Check git log for changes to TransactionCache or connection pool config.\n"
            "3. Execute rollback to previous stable version.\n"
            "4. Wait 2 minutes for memory to stabilise below 65%.\n"
            "5. Verify error rate returns below 2.5/min.\n"
            "6. Document regression in post-mortem with commit hash."
        ),
        "runbook_text": (
            "Apply when payment-service shows steadily climbing memory usage after a recent deployment. "
            "Symptoms include: JVM heap growing without plateau, GC pause times increasing, "
            "TransactionCache or JDBC connection pool log warnings, memory utilization above 70% "
            "and rising at more than 1% per minute. "
            "If a deployment occurred within the last 90 minutes, rollback is the correct first action — "
            "do not attempt a service restart, as the leak will recur immediately on the same code. "
            "Rollback is safe when you have a known-good previous version. "
            "Risk is medium because rollback causes a brief request spike during restart. "
            "Estimated resolution: 3 minutes from trigger to memory stabilisation."
        ),
    },
    {
        "runbook_id": "rb-002",
        "title": "Service memory exhaustion — restart when no recent deployment",
        "service": "any",
        "action_type": "restart_service",
        "risk_level": "low",
        "estimated_time_minutes": 1,
        "steps": (
            "1. Confirm no deployment in the last 2 hours.\n"
            "2. Capture heap dump or memory profile if possible.\n"
            "3. Restart the service container.\n"
            "4. Monitor memory for 5 minutes post-restart to confirm stabilisation.\n"
            "5. If memory climbs again within 30 minutes, escalate to engineering — "
            "likely a latent leak that needs a code fix."
        ),
        "runbook_text": (
            "Apply when any service shows high memory utilization or heap exhaustion "
            "without a recent deployment to blame. "
            "Symptoms: container approaching OOM kill threshold, RSS growing beyond configured limits, "
            "out of memory errors in application logs, GC thrashing, process memory growing past 85%. "
            "When there is no recent deployment, a service restart clears the leaked objects and "
            "restores normal operation temporarily. This is a low-risk, fast action. "
            "However, if memory starts climbing again after restart, the leak is latent in the existing "
            "codebase and requires engineering intervention. "
            "Estimated resolution: under 1 minute."
        ),
    },
    {
        "runbook_id": "rb-003",
        "title": "Auth service error spike — Redis cache offline, restart dependency",
        "service": "auth-service",
        "action_type": "restart_dependency",
        "risk_level": "low",
        "estimated_time_minutes": 2,
        "steps": (
            "1. Confirm Redis is unreachable (check CACHE_OFFLINE error code in logs).\n"
            "2. Check Redis container health: docker ps | grep auth-redis.\n"
            "3. Restart auth-redis container.\n"
            "4. Wait for Redis to accept connections (typically 15–20 seconds).\n"
            "5. Confirm auth-service error rate drops below 2/min within 60 seconds.\n"
            "6. If Redis restarts but errors persist, check auth-service cache reconnection logic."
        ),
        "runbook_text": (
            "Apply when auth-service shows a sudden sharp error rate spike with log errors "
            "indicating cache unavailability or session lookup failures. "
            "Symptoms: CACHE_OFFLINE error code appearing in auth logs, "
            "error rate jumping from normal baseline to 15–30 errors per minute, "
            "session validation timeouts, users unable to authenticate, "
            "auth-service falling back to slow database lookups causing latency spikes. "
            "Root cause is typically Redis cache eviction, OOM kill, or network partition. "
            "Restarting the Redis dependency is the correct first action — do not restart auth-service itself, "
            "as it is functioning correctly but degraded by the missing cache layer. "
            "Risk is low as Redis restart is non-destructive to auth-service state. "
            "Estimated resolution: 2 minutes."
        ),
    },
    {
        "runbook_id": "rb-004",
        "title": "Error spike after deployment — rollback to previous version",
        "service": "any",
        "action_type": "rollback_deployment",
        "risk_level": "medium",
        "estimated_time_minutes": 3,
        "steps": (
            "1. Identify the deployment that correlates with error spike onset.\n"
            "2. Confirm error rate exceeded 3x normal baseline after deploy timestamp.\n"
            "3. Check logs for specific exception type (NPE, serialisation error, connection failure).\n"
            "4. Execute rollback to the previous stable version.\n"
            "5. Confirm error rate returns to baseline within 2 minutes.\n"
            "6. File a bug with the specific exception stack trace from the failed deployment."
        ),
        "runbook_text": (
            "Apply when any service shows a sudden error rate spike that correlates directly "
            "with a recent deployment event. "
            "Symptoms: error rate rising sharply within 5 minutes of a deployment, "
            "application exceptions in logs such as NullPointerException, serialisation failures, "
            "missing configuration errors, or contract violations, "
            "error rate 3x or more above the normal baseline, "
            "errors affecting the same code path that was changed in the deployment. "
            "A deployment-correlated error spike almost always means code regression. "
            "Rollback is the correct action — faster and safer than attempting a hotfix under pressure. "
            "Risk is medium due to the brief outage window during rollback. "
            "Estimated resolution: 3 minutes."
        ),
    },
    {
        "runbook_id": "rb-005",
        "title": "Checkout service serialisation or null pointer errors after version bump",
        "service": "checkout-service",
        "action_type": "rollback_deployment",
        "risk_level": "medium",
        "estimated_time_minutes": 3,
        "steps": (
            "1. Confirm error logs show NullPointerException, ClassCastException, or serialisation errors.\n"
            "2. Check which checkout-service version was deployed and when.\n"
            "3. Look for changes to cart model, order serialiser, or payment integration in the diff.\n"
            "4. Rollback to the previous stable version.\n"
            "5. Verify checkout flow is healthy: error rate < 1/min, latency < 200ms.\n"
            "6. Fix the null pointer or serialisation issue in a feature branch with tests before re-deploying."
        ),
        "runbook_text": (
            "Apply when checkout-service shows exceptions related to cart serialisation, "
            "null pointer dereferences, or type casting failures after a version bump. "
            "Symptoms: NullPointerException or ClassCastException in checkout logs, "
            "order processing failures, cart data corrupted or missing fields, "
            "payment integration errors due to unexpected data shape, "
            "error rate spiking immediately following a deployment of a new checkout version. "
            "These errors indicate a code regression in the cart or order processing pipeline. "
            "Rollback is safe and fast. The bug should be reproduced in a test environment before re-deploying. "
            "Estimated resolution: 3 minutes."
        ),
    },
    {
        "runbook_id": "rb-006",
        "title": "Memory pressure under high traffic — scale cache layer",
        "service": "any",
        "action_type": "scale_cache",
        "risk_level": "medium",
        "estimated_time_minutes": 5,
        "steps": (
            "1. Confirm memory pressure correlates with traffic spike (check requests_per_min metric).\n"
            "2. Check cache hit ratio in logs — if below 70%, cache is undersized.\n"
            "3. Increase cache allocation: scale cache layer horizontally or increase max memory.\n"
            "4. If using Redis, increase maxmemory config and restart Redis with new setting.\n"
            "5. Monitor memory over next 10 minutes — should stabilise as cache absorbs reads.\n"
            "6. Consider adding a circuit breaker to prevent cache bypass under high load."
        ),
        "runbook_text": (
            "Apply when a service shows memory pressure that correlates with increased request volume "
            "rather than a deployment or code change. "
            "Symptoms: memory utilization rising during peak traffic windows, "
            "cache eviction rate high (objects being evicted before natural TTL), "
            "cache hit ratio dropping below 70%, "
            "requests falling through to the database causing latency spikes, "
            "memory growing as the application allocates more heap to handle uncached requests. "
            "This pattern indicates the cache is undersized for current traffic load — "
            "not a memory leak. Scaling the cache layer reduces heap pressure by keeping hot data "
            "in the cache rather than re-allocating it on every request. "
            "Risk is medium — scaling cache requires a brief restart of the cache process. "
            "Estimated resolution: 5 minutes."
        ),
    },
    {
        "runbook_id": "rb-007",
        "title": "JVM heap pressure and GC thrashing — restart service",
        "service": "any",
        "action_type": "restart_service",
        "risk_level": "low",
        "estimated_time_minutes": 1,
        "steps": (
            "1. Confirm GC pause times are elevated (look for GC log messages or latency spikes).\n"
            "2. Confirm no recent deployment.\n"
            "3. Restart the service — this clears the heap and stops GC thrashing immediately.\n"
            "4. If GC thrashing recurs, consider tuning heap size (Xmx) or switching GC algorithm.\n"
            "5. Capture GC logs before restart if possible for offline analysis."
        ),
        "runbook_text": (
            "Apply when a JVM-based service shows increasing GC pause times, "
            "stop-the-world collection events, or throughput degradation due to heap pressure. "
            "Symptoms: GC pause times above 500ms, old generation heap filling to capacity, "
            "request latency spikes that correlate with GC events, "
            "application throughput dropping as GC competes for CPU, "
            "heap dump analysis showing long-lived objects accumulating in old generation. "
            "GC thrashing typically indicates that the heap is too small for the current working set, "
            "or that objects are not being reclaimed due to lingering references. "
            "A service restart clears the heap immediately. "
            "If the issue recurs, investigate object retention patterns and consider increasing heap allocation. "
            "Risk is low. Estimated resolution: under 1 minute."
        ),
    },
    {
        "runbook_id": "rb-008",
        "title": "Error rate spike with unclear root cause — restart dependency",
        "service": "any",
        "action_type": "restart_dependency",
        "risk_level": "medium",
        "estimated_time_minutes": 2,
        "steps": (
            "1. Check logs for errors pointing to a specific downstream dependency (cache, DB, queue).\n"
            "2. Check connectivity to each dependency.\n"
            "3. Restart the dependency that appears degraded or unresponsive.\n"
            "4. If no specific dependency is implicated, escalate to engineering.\n"
            "5. Monitor error rate for 2 minutes after restart to confirm recovery."
        ),
        "runbook_text": (
            "Apply when a service shows an error rate spike without a clear deployment trigger "
            "and without obvious code regression in logs. "
            "Symptoms: sudden increase in error rate without a correlated deployment, "
            "timeout errors pointing to downstream services, "
            "connection refused or connection reset errors in application logs, "
            "dependency health checks failing, "
            "errors resolving on their own briefly then returning — suggesting a flapping dependency. "
            "When the root cause points to a downstream dependency (cache, message queue, database replica), "
            "restarting that dependency is the correct first action. "
            "If after restart errors persist or no dependency is clearly at fault, escalate — "
            "this may require infrastructure investigation beyond automated remediation. "
            "Risk is medium as dependency restart may briefly affect all services using it. "
            "Estimated resolution: 2 minutes."
        ),
    },
]


def get_es() -> Elasticsearch:
    if ELASTIC_CLOUD_ID:
        return Elasticsearch(
            cloud_id=ELASTIC_CLOUD_ID,
            api_key=ELASTIC_API_KEY,
            request_timeout=60,
        )
    return Elasticsearch(ELASTIC_URL, api_key=ELASTIC_API_KEY, request_timeout=60)


def seed():
    print("\n📚 QuantumState — Runbook Seeder\n")

    es = get_es()

    # Create index
    if es.indices.exists(index=INDEX):
        print(f"ℹ  Index {INDEX!r} already exists — skipping creation.")
    else:
        try:
            es.indices.create(index=INDEX, body=INDEX_BODY)
            print(f"✅ Created index: {INDEX}")
        except Exception as exc:
            sys.exit(
                f"ERROR creating index: {exc}\n"
                f"  Make sure ELSER is deployed first:\n"
                f"    python elastic-setup/setup_elser.py"
            )

    # Seed runbooks
    print(f"\nSeeding {len(RUNBOOKS)} runbooks...")
    ok = 0
    for rb in RUNBOOKS:
        try:
            es.index(index=INDEX, id=rb["runbook_id"], document=rb, refresh=True)
            print(f"  ✅ {rb['runbook_id']}: {rb['title']}")
            ok += 1
        except Exception as exc:
            print(f"  ❌ {rb['runbook_id']}: {exc}")

    print(f"\n✅ Done. {ok}/{len(RUNBOOKS)} runbooks indexed in {INDEX!r}.\n")


def teardown():
    print(f"\n🗑️  Deleting index: {INDEX}\n")
    es = get_es()
    try:
        if es.indices.exists(index=INDEX):
            es.indices.delete(index=INDEX)
            print(f"✅ Deleted {INDEX}")
        else:
            print(f"ℹ  Index {INDEX!r} not found — nothing to delete.")
    except Exception as exc:
        print(f"❌ Error: {exc}")
    print()


if __name__ == "__main__":
    if not ELASTIC_API_KEY:
        sys.exit("ERROR: ELASTIC_API_KEY not set in .env")
    if not ELASTIC_CLOUD_ID and not ELASTIC_URL:
        sys.exit("ERROR: Set ELASTIC_CLOUD_ID or ELASTIC_URL in .env")

    parser = argparse.ArgumentParser(description="QuantumState runbook seeder")
    parser.add_argument("--delete", action="store_true", help="Delete the runbooks index")
    args = parser.parse_args()

    if args.delete:
        teardown()
    else:
        seed()
