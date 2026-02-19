"""POST /api/sim/* — Simulation Control endpoints."""
import os
import sys
import math
import random
import threading
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from inject import inject_memory_leak, inject_deployment_rollback, inject_error_spike
from elastic import get_es

router = APIRouter(prefix="/sim", tags=["sim"])

# ── Shared streamer state ──────────────────────────────────────────────────────

_stream_thread: threading.Thread | None = None
_stream_stop:   threading.Event  | None = None
_stream_lock = threading.Lock()

SERVICES = [
    {"name": "payment-service",   "region": "us-east-1"},
    {"name": "checkout-service",  "region": "us-east-1"},
    {"name": "auth-service",      "region": "us-west-2"},
    {"name": "inventory-service", "region": "eu-west-1"},
]

BASELINES = {
    "memory_percent": {"mean": 52, "std": 4},
    "cpu_percent":    {"mean": 35, "std": 8},
    "error_rate":     {"mean": 0.4, "std": 0.2},
    "latency_ms":     {"mean": 120, "std": 25},
    "requests_per_min": {"mean": 850, "std": 120},
}

METRIC_UNITS = {
    "memory_percent":     "percent",
    "cpu_percent":        "percent",
    "error_rate":         "errors_per_min",
    "latency_ms": "ms",
    "requests_per_min":   "requests_per_min",
}

QUANTUMSTATE_INDICES = {
    "metrics-quantumstate": {
        "mappings": {"properties": {
            "@timestamp": {"type": "date"}, "service": {"type": "keyword"},
            "region": {"type": "keyword"}, "metric_type": {"type": "keyword"},
            "value": {"type": "double"}, "unit": {"type": "keyword"},
        }}
    },
    "logs-quantumstate": {
        "mappings": {"properties": {
            "@timestamp": {"type": "date"}, "service": {"type": "keyword"},
            "region": {"type": "keyword"}, "level": {"type": "keyword"},
            "message": {"type": "text"}, "trace_id": {"type": "keyword"},
            "error_code": {"type": "keyword"},
        }}
    },
    "incidents-quantumstate": {
        "mappings": {"properties": {
            "@timestamp":         {"type": "date"},
            "service":            {"type": "keyword"},
            "region":             {"type": "keyword"},
            "anomaly_type":       {"type": "keyword"},
            "root_cause":         {"type": "text"},
            "action_taken":       {"type": "text"},
            "recommended_action": {"type": "keyword"},
            "confidence_score":   {"type": "float"},
            "risk_level":         {"type": "keyword"},
            "resolved_at":        {"type": "date"},
            "mttr_seconds":       {"type": "integer"},
            "mttr_estimate":      {"type": "keyword"},
            "status":             {"type": "keyword"},
            "resolution_status":  {"type": "keyword"},
            "pipeline_run":       {"type": "boolean"},
            "pipeline_summary":   {"type": "text"},
            "guardian_verified":  {"type": "boolean"},
            "lessons_learned":    {"type": "text"},
            # semantic_text — ELSER embeds this for hybrid search by find_similar_incidents
            # Requires setup_elser.py to be run before index creation
            "incident_text": {
                "type":         "semantic_text",
                "inference_id": ".elser-2-elasticsearch",
            },
        }}
    },
    "agent-decisions-quantumstate": {
        "mappings": {"properties": {
            "@timestamp": {"type": "date"}, "agent": {"type": "keyword"},
            "decision": {"type": "text"}, "confidence": {"type": "integer"},
            "service": {"type": "keyword"},
            "context": {"type": "object", "enabled": False},
        }}
    },
    "remediation-actions-quantumstate": {
        "mappings": {"properties": {
            "@timestamp":      {"type": "date"},
            "incident_id":     {"type": "keyword"},
            "service":         {"type": "keyword"},
            "action":          {"type": "keyword"},
            "anomaly_type":    {"type": "keyword"},
            "confidence_score":{"type": "float"},
            "risk_level":      {"type": "keyword"},
            "triggered_by":    {"type": "keyword"},
            "status":          {"type": "keyword"},
            "exec_id":         {"type": "keyword"},
            "executed_at":     {"type": "date"},
            "workflow_triggered": {"type": "boolean"},
            "case_id":         {"type": "keyword"},
            "root_cause":      {"type": "text"},
        }}
    },
    "remediation-results-quantumstate": {
        "mappings": {"properties": {
            "@timestamp":      {"type": "date"},
            "incident_id":     {"type": "keyword"},
            "service":         {"type": "keyword"},
            "action":          {"type": "keyword"},
            "exec_id":         {"type": "keyword"},
            "outcome":         {"type": "keyword"},
            "recovery_initiated": {"type": "boolean"},
        }}
    },
    "runbooks-quantumstate": {
        "mappings": {"properties": {
            "runbook_id":             {"type": "keyword"},
            "title":                  {"type": "text"},
            "service":                {"type": "keyword"},
            "action_type":            {"type": "keyword"},
            "risk_level":             {"type": "keyword"},
            "estimated_time_minutes": {"type": "integer"},
            "steps":                  {"type": "text"},
            "runbook_text": {
                "type":         "semantic_text",
                "inference_id": ".elser-2-elasticsearch",
            },
        }}
    },
}

PAST_INCIDENTS = [
    # ── Memory leak incidents (35) ─────────────────────────────────────────────
    {
        "service": "payment-service", "region": "us-east-1",
        "anomaly_type": "memory_leak_progressive",
        "root_cause": "Memory leak in JDBC connection pool introduced by deploy v2.1.0. Pool objects not released after transaction rollback.",
        "action_taken": "Rolled back to v2.0.9. Memory stabilised at 52% within 4 minutes.",
        "mttr_seconds": 2820, "days_ago": 14,
        "incident_text": "payment-service JVM heap climbing steadily after v2.1.0 deployment. JDBC connection pool objects retained after transaction rollback, causing progressive heap exhaustion. GC unable to reclaim retained connections. Resolved by rollback to v2.0.9 — memory stabilised within 4 minutes.",
    },
    {
        "service": "inventory-service", "region": "eu-west-1",
        "anomaly_type": "memory_leak_progressive",
        "root_cause": "Unbounded in-memory cache for product catalogue with no eviction policy.",
        "action_taken": "Added LRU eviction limit (max 10k entries). Deployed hotfix v1.8.3.",
        "mttr_seconds": 5400, "days_ago": 21,
        "incident_text": "inventory-service memory growing continuously over 90 minutes. In-memory product catalogue cache had no size bound, accumulating entries indefinitely. Container RSS approaching OOM kill threshold. Fixed by adding LRU eviction in hotfix v1.8.3.",
    },
    {
        "service": "checkout-service", "region": "us-east-1",
        "anomaly_type": "memory_leak_progressive",
        "root_cause": "ThreadLocal request context not cleared after request completion, accumulating large cart objects across threads.",
        "action_taken": "Patched request filter to always call ThreadLocal.remove() in finally block. Restarted service to clear existing heap.",
        "mttr_seconds": 3600, "days_ago": 35,
        "incident_text": "checkout-service heap filling over 2 hours. ThreadLocal variables holding cart context objects not cleared at request end. Objects promoted to old generation and never collected. Service restarted; hotfix added finally-block cleanup to request filter.",
    },
    {
        "service": "auth-service", "region": "us-west-2",
        "anomaly_type": "memory_leak_progressive",
        "root_cause": "File descriptor leak in HTTP client — connections opened to token validation endpoint without being closed.",
        "action_taken": "Switched to connection-pool-aware HTTP client. Restarted auth-service.",
        "mttr_seconds": 1800, "days_ago": 45,
        "incident_text": "auth-service memory and file descriptor count climbing. HTTP client opened connections to upstream token validator but never closed them. OS file descriptor limit approached, causing connection refused errors. Restarted service, replaced HTTP client with pooled variant.",
    },
    {
        "service": "payment-service", "region": "us-east-1",
        "anomaly_type": "memory_leak_progressive",
        "root_cause": "Byte buffer accumulation in streaming payment processor. Buffers allocated for each transaction chunk not returned to pool.",
        "action_taken": "Fixed buffer lifecycle in payment processor. Restarted service.",
        "mttr_seconds": 2100, "days_ago": 50,
        "incident_text": "payment-service off-heap memory growing during high transaction volume. Byte buffers allocated per transaction chunk not returned to Netty buffer pool after use. Direct memory pressure triggering OutOfDirectMemoryError. Restart cleared state; buffer lifecycle corrected in subsequent patch.",
    },
    {
        "service": "payment-service", "region": "us-east-1",
        "anomaly_type": "memory_leak_progressive",
        "root_cause": "LRU cache eviction disabled by misconfigured deploy — max_entries set to Integer.MAX_VALUE.",
        "action_taken": "Corrected cache config. Deployed hotfix. Restarted service.",
        "mttr_seconds": 1440, "days_ago": 62,
        "incident_text": "payment-service heap growing after config change deployment. LRU cache eviction disabled: max_entries set to Integer.MAX_VALUE in environment variable override. Cache grew without bound, filling old generation heap. Corrected config and redeployed; service restarted to clear retained objects.",
    },
    {
        "service": "auth-service", "region": "us-west-2",
        "anomaly_type": "memory_leak_progressive",
        "root_cause": "Session objects retained in memory after logout. SessionRegistry holding strong references preventing GC.",
        "action_taken": "Fixed SessionRegistry cleanup on logout. Service restarted.",
        "mttr_seconds": 3240, "days_ago": 72,
        "incident_text": "auth-service heap climbing across login/logout cycle. SessionRegistry maintaining strong references to session objects after logout events. Sessions never evicted from registry, accumulating indefinitely. GC pressure increasing over several hours. Patched logout handler to deregister sessions; service restarted.",
    },
    {
        "service": "checkout-service", "region": "us-east-1",
        "anomaly_type": "memory_leak_progressive",
        "root_cause": "Object pool for cart pricing calculators not returning instances after pricing runs.",
        "action_taken": "Fixed pool return logic. Service restarted to clear accumulated objects.",
        "mttr_seconds": 2880, "days_ago": 80,
        "incident_text": "checkout-service memory increasing across pricing calculation spikes. Object pool for cart calculators not receiving returned instances after use — objects accumulating outside pool. Heap occupancy growing 1% per minute under load. Service restarted; pool return bug fixed in pricing module.",
    },
    {
        "service": "inventory-service", "region": "eu-west-1",
        "anomaly_type": "memory_leak_progressive",
        "root_cause": "JDBC ResultSet and Statement objects not closed in legacy query path. Connection leak filling pool.",
        "action_taken": "Refactored legacy query path to use try-with-resources. Restarted service.",
        "mttr_seconds": 4200, "days_ago": 91,
        "incident_text": "inventory-service database connection pool exhausted, triggering memory pressure. Legacy query path not closing JDBC ResultSet and Statement objects. Connections accumulated, pool filled, and JVM allocated additional heap buffers for pending requests. Refactored to try-with-resources pattern.",
    },
    {
        "service": "payment-service", "region": "us-east-1",
        "anomaly_type": "memory_leak_progressive",
        "root_cause": "WebSocket connections to payment terminal not closed after transaction timeout.",
        "action_taken": "Added connection cleanup on timeout path. Restarted service.",
        "mttr_seconds": 1920, "days_ago": 105,
        "incident_text": "payment-service memory growing during periods of terminal timeouts. WebSocket connections kept open after transaction timeout rather than being closed. Each timed-out connection retained session state objects in heap. Service restarted; connection teardown added to timeout handler.",
    },
    {
        "service": "checkout-service", "region": "us-east-1",
        "anomaly_type": "memory_leak_progressive",
        "root_cause": "Static HashMap used to track active checkout sessions, never cleaned up on session expiry.",
        "action_taken": "Replaced static HashMap with TTL-based ConcurrentMap. Restarted.",
        "mttr_seconds": 2640, "days_ago": 118,
        "incident_text": "checkout-service heap growing steadily. Static HashMap tracking active checkout sessions not cleared when sessions expired. Map accumulated thousands of stale entries over time, each holding serialised cart state. Memory growing 0.8% per hour. Replaced with TTL-evicting cache; service restarted.",
    },
    {
        "service": "auth-service", "region": "us-west-2",
        "anomaly_type": "memory_leak_progressive",
        "root_cause": "Container RSS exceeding cgroup memory limit after gradual growth over 12 hours. No single large object — accumulated retained token metadata.",
        "action_taken": "Restarted auth-service. Added memory alerting at 70% to catch earlier.",
        "mttr_seconds": 720, "days_ago": 125,
        "incident_text": "auth-service container RSS grew to cgroup memory limit over 12 hours. Accumulated small token metadata objects in a growing HashMap were never cleared. No obvious large allocation — death by a thousand small leaks. OOM kill avoided by proactive restart. Alerting threshold lowered to 70%.",
    },
    {
        "service": "inventory-service", "region": "eu-west-1",
        "anomaly_type": "memory_leak_progressive",
        "root_cause": "GC old generation filling due to event listener registration without deregistration in stock update pipeline.",
        "action_taken": "Fixed listener lifecycle. Deployed patch v2.1.4.",
        "mttr_seconds": 5760, "days_ago": 133,
        "incident_text": "inventory-service GC old generation reaching 95% capacity. Stock update pipeline registered event listeners on every update without deregistering. Listeners held references to update context objects, preventing GC. Old generation filled over 8 hours. Patched listener lifecycle management.",
    },
    {
        "service": "payment-service", "region": "us-east-1",
        "anomaly_type": "memory_leak_progressive",
        "root_cause": "Container approaching OOM kill threshold. Tomcat thread pool holding idle thread stacks at 512KB each with 200 threads configured.",
        "action_taken": "Reduced Tomcat max threads to 50. Restarted.",
        "mttr_seconds": 1080, "days_ago": 140,
        "incident_text": "payment-service approaching OOM kill. Tomcat configured with 200 max threads — idle thread stacks consuming 100MB of heap at rest. Under load threads allocated additional per-request buffers, compounding pressure. Reduced thread pool to 50. Service restarted to release accumulated stack memory.",
    },
    {
        "service": "payment-service", "region": "us-east-1",
        "anomaly_type": "memory_leak_progressive",
        "root_cause": "Memory growing 1.5% per minute after deploy v2.3.0. TransactionAuditCache had max_size removed in refactor.",
        "action_taken": "Rolled back to v2.2.8.",
        "mttr_seconds": 960, "days_ago": 7,
        "incident_text": "payment-service memory climbing at 1.5% per minute after v2.3.0 deployment. Code review found max_size parameter removed from TransactionAuditCache during refactor — cache growing without bound. Immediate rollback to v2.2.8 resolved the issue within 2 minutes.",
    },
    {
        "service": "payment-service", "region": "us-east-1",
        "anomaly_type": "memory_leak_progressive",
        "root_cause": "JVM heap exhaustion in payment processor. Large payment batches retained in memory while awaiting settlement confirmation.",
        "action_taken": "Restarted service. Implemented streaming processing for large batches.",
        "mttr_seconds": 1800, "days_ago": 28,
        "incident_text": "payment-service JVM heap exhausted during batch settlement window. Payment batches fully loaded into heap before processing, with large batches consuming 2-4GB. With multiple concurrent batches, heap exhausted. Service restarted; streaming batch processor implemented to avoid full in-memory load.",
    },
    {
        "service": "checkout-service", "region": "us-east-1",
        "anomaly_type": "memory_leak_progressive",
        "root_cause": "Prometheus metrics buffer not flushed — label cardinality explosion from user-specific metric labels.",
        "action_taken": "Removed user-specific labels from metrics. Restarted service.",
        "mttr_seconds": 2520, "days_ago": 42,
        "incident_text": "checkout-service memory growing due to Prometheus metrics label cardinality explosion. Metrics incorrectly included user ID as a label, creating a unique time series per user. Millions of label combinations accumulated in the metrics buffer. Removed user-specific labels; service restarted to clear the buffer.",
    },
    {
        "service": "auth-service", "region": "us-west-2",
        "anomaly_type": "memory_leak_progressive",
        "root_cause": "Netty OffHeap buffer pool accumulation. ByteBuf objects not released after token decryption operations.",
        "action_taken": "Added reference-counted release to token decryption path. Restarted.",
        "mttr_seconds": 3000, "days_ago": 55,
        "incident_text": "auth-service direct memory growing. Netty ByteBuf objects allocated for token decryption not released after use — reference counts never decremented to trigger pool return. Direct memory grew steadily until JVM threw OutOfDirectMemoryError. Patched decryption path with explicit release; service restarted.",
    },
    {
        "service": "inventory-service", "region": "eu-west-1",
        "anomaly_type": "memory_leak_progressive",
        "root_cause": "Per-request temporary files for product image processing not deleted after response sent.",
        "action_taken": "Added cleanup in response filter. Restarted service.",
        "mttr_seconds": 2160, "days_ago": 67,
        "incident_text": "inventory-service memory and disk growing. Product image processing created temporary files per request but cleanup only ran on success path — errors left files on disk and in-memory references in a tracking list. List grew unbounded. Cleanup moved to finally block; service restarted.",
    },
    {
        "service": "payment-service", "region": "us-east-1",
        "anomaly_type": "memory_leak_progressive",
        "root_cause": "Connection multiplexer holding stale connections to payment gateway — eviction TTL set to 0 (disabled) in config.",
        "action_taken": "Set connection TTL to 5 minutes. Restarted service.",
        "mttr_seconds": 1560, "days_ago": 77,
        "incident_text": "payment-service heap growing with network connections. HTTP/2 connection multiplexer retained stale connections to payment gateway — eviction TTL accidentally set to zero in config, effectively disabling eviction. Thousands of closed connections held in memory. Config corrected; service restarted.",
    },
    {
        "service": "checkout-service", "region": "us-east-1",
        "anomaly_type": "memory_leak_progressive",
        "root_cause": "Hibernate second-level cache growing unbounded. Cache region for CartItem had no max size or TTL configured.",
        "action_taken": "Added max_size=5000 and TTL=300s to CartItem cache region. Restarted.",
        "mttr_seconds": 3960, "days_ago": 88,
        "incident_text": "checkout-service Hibernate second-level cache filling JVM heap. CartItem cache region had no size limit or TTL — every CartItem ever queried accumulated in the cache across all sessions. Heap grew 2% per hour during business hours. Cache region bounded and TTL added; service restarted.",
    },
    {
        "service": "auth-service", "region": "us-west-2",
        "anomaly_type": "memory_leak_progressive",
        "root_cause": "Native memory leak in JNI crypto library. After upgrade to libssl v3, cleanup function not called correctly from JNI wrapper.",
        "action_taken": "Fixed JNI cleanup call. Redeployed. Service restarted.",
        "mttr_seconds": 5040, "days_ago": 97,
        "incident_text": "auth-service native memory growing outside JVM heap. JNI wrapper for libssl v3 missing cleanup call after TLS handshake context disposal. Native allocations accumulated, visible in process RSS but not JVM heap metrics. Detected via container memory stats. JNI cleanup fixed; service redeployed.",
    },
    {
        "service": "inventory-service", "region": "eu-west-1",
        "anomaly_type": "memory_leak_progressive",
        "root_cause": "EventBus listener registration on every HTTP request without cleanup — listeners accumulating.",
        "action_taken": "Moved listener registration to application startup. Restarted.",
        "mttr_seconds": 2880, "days_ago": 109,
        "incident_text": "inventory-service memory growing proportionally to request count. EventBus listeners registered on each incoming request rather than at startup. Each listener held reference to request context objects. After millions of requests, thousands of listeners accumulated. Registration moved to startup; service restarted.",
    },
    {
        "service": "payment-service", "region": "us-east-1",
        "anomaly_type": "memory_leak_progressive",
        "root_cause": "Tomcat request thread pool creating per-thread MDC context maps not cleared on thread return to pool.",
        "action_taken": "Added MDC.clear() to request interceptor finally block. Restarted.",
        "mttr_seconds": 2040, "days_ago": 115,
        "incident_text": "payment-service JVM heap growing in the Tomcat thread pool. MDC (Mapped Diagnostic Context) maps attached to each thread not cleared when thread returned to pool. Over thousands of requests, each thread accumulated a large MDC map. Memory grew proportionally to active thread pool size. Cleared on thread return.",
    },
    {
        "service": "checkout-service", "region": "us-east-1",
        "anomaly_type": "memory_leak_progressive",
        "root_cause": "JVM compressed OOPs disabled by JVM flag added in deploy, increasing pointer size and inflating heap usage significantly.",
        "action_taken": "Removed erroneous JVM flag. Restarted service.",
        "mttr_seconds": 720, "days_ago": 122,
        "incident_text": "checkout-service JVM heap growing after deploy. Investigation found -XX:-UseCompressedOops flag added to JVM args — disabled compressed object pointers, increasing pointer size from 32-bit to 64-bit. All object references doubled in size, inflating heap by ~30%. Erroneous flag removed; service restarted.",
    },
    {
        "service": "auth-service", "region": "us-west-2",
        "anomaly_type": "memory_leak_progressive",
        "root_cause": "Weak references promoted to strong retention via closure capture in permission cache loader.",
        "action_taken": "Refactored cache loader to avoid closure capture. Restarted.",
        "mttr_seconds": 3600, "days_ago": 131,
        "incident_text": "auth-service permission cache growing beyond expected bounds. Cache loader closure captured a reference to the parent config object, which itself held the cache — creating a retention cycle that prevented GC of evicted entries. Objects promoted to old generation and never collected. Refactored cache loader.",
    },
    {
        "service": "inventory-service", "region": "eu-west-1",
        "anomaly_type": "memory_leak_progressive",
        "root_cause": "RxJava observables subscribed per inventory query without disposing subscriptions on timeout.",
        "action_taken": "Added CompositeDisposable cleanup on timeout path. Restarted.",
        "mttr_seconds": 3240, "days_ago": 145,
        "incident_text": "inventory-service memory growing during peak query periods. RxJava observables created per inventory batch query, subscriptions not disposed on timeout. Timeout path returned empty results but did not clean up the subscription — subscribed objects retained in heap. Cleanup added to timeout handler.",
    },
    {
        "service": "payment-service", "region": "us-east-1",
        "anomaly_type": "memory_leak_progressive",
        "root_cause": "Logback async appender queue growing unbounded during log burst. Queue size set to 0 (unlimited) in config.",
        "action_taken": "Set async appender queue size to 512. Restarted service.",
        "mttr_seconds": 1320, "days_ago": 155,
        "incident_text": "payment-service heap growing during high-volume transaction periods. Logback async appender queue size set to 0 (unlimited). Log bursts during peak processing filled the queue with thousands of log events, each holding references to the transaction context. Queue bounded to 512 entries; service restarted.",
    },
    {
        "service": "checkout-service", "region": "us-east-1",
        "anomaly_type": "memory_leak_progressive",
        "root_cause": "Kafka consumer offset tracking kept entirely in-memory with no commit, causing accumulated lag tracking objects.",
        "action_taken": "Enabled Kafka offset commit. Restarted consumer.",
        "mttr_seconds": 2400, "days_ago": 162,
        "incident_text": "checkout-service Kafka consumer memory growing. Offset tracking maintained entirely in-memory without committing to Kafka. In-memory offset map accumulated partition metadata across all consumed messages. Memory grew 5MB per hour at normal throughput. Kafka offset commit enabled; consumer restarted.",
    },
    {
        "service": "auth-service", "region": "us-west-2",
        "anomaly_type": "memory_leak_progressive",
        "root_cause": "Task queue growing without bound under sustained auth verification load.",
        "action_taken": "Added bounded executor queue (capacity 1000). Shed excess load. Restarted.",
        "mttr_seconds": 1680, "days_ago": 168,
        "incident_text": "auth-service memory growing under sustained verification load. Async task executor using unbounded LinkedBlockingQueue — tasks queued faster than they were processed during peak auth events. Queue accumulated tens of thousands of pending verification tasks, each holding request payload. Bounded queue applied; service restarted.",
    },
    {
        "service": "inventory-service", "region": "eu-west-1",
        "anomaly_type": "memory_leak_progressive",
        "root_cause": "SoftReference-based cache not releasing under memory pressure due to JVM -XX:SoftRefLRUPolicyMSPerMB=0 setting.",
        "action_taken": "Removed problematic JVM flag. Restarted service.",
        "mttr_seconds": 2760, "days_ago": 175,
        "incident_text": "inventory-service SoftReference cache not evicting under heap pressure. JVM flag -XX:SoftRefLRUPolicyMSPerMB set to 0 made soft references nearly as strong as hard references, preventing eviction under memory pressure. Cache grew until OOM. JVM flag removed; JVM now evicts soft refs aggressively under pressure.",
    },
    {
        "service": "payment-service", "region": "us-east-1",
        "anomaly_type": "memory_leak_progressive",
        "root_cause": "Guava cache constructed without maximumSize or expireAfterWrite — effectively an unbounded Map.",
        "action_taken": "Added maximumSize(50000) and expireAfterWrite(1h). Hotfix deployed.",
        "mttr_seconds": 2160, "days_ago": 60,
        "incident_text": "payment-service Guava cache growing without bound. Cache for resolved payment method metadata constructed without maximumSize or TTL — functionally equivalent to a HashMap that never evicts. Each unique payment method ID added a permanent entry. Memory grew 10MB per hour at normal load. Bounded cache deployed.",
    },
    {
        "service": "checkout-service", "region": "us-east-1",
        "anomaly_type": "memory_leak_progressive",
        "root_cause": "JVM Metaspace exhaustion due to dynamic proxy class generation — one new class per request in legacy AOP component.",
        "action_taken": "Fixed dynamic proxy to reuse generated classes. Restarted service.",
        "mttr_seconds": 3480, "days_ago": 85,
        "incident_text": "checkout-service JVM Metaspace growing to exhaustion. Legacy AOP component generated a new dynamic proxy class per incoming request. Metaspace grew until OutOfMemoryError: Metaspace. Classes are not GC'd unless their ClassLoader is collected — which never happened for the shared AOP ClassLoader. Fixed proxy reuse.",
    },
    {
        "service": "auth-service", "region": "us-west-2",
        "anomaly_type": "memory_leak_progressive",
        "root_cause": "EhCache disk overflow disabled — all overflow went to heap. Disk overflow configuration removed in migration.",
        "action_taken": "Restored disk overflow config. Restarted service.",
        "mttr_seconds": 2880, "days_ago": 100,
        "incident_text": "auth-service heap saturating under high session load. EhCache configured to overflow to disk when heap quota exceeded, but disk overflow was removed during a config migration. All cache overflow went to heap instead. Session cache grew beyond heap allocation. Disk overflow restored; service restarted.",
    },
    {
        "service": "inventory-service", "region": "eu-west-1",
        "anomaly_type": "memory_leak_progressive",
        "root_cause": "Memory ratcheting under sustained load after v1.9.0 deployed. Stock reservation objects not recycled after reservation expiry.",
        "action_taken": "Rolled back to v1.8.9. Issued fix in v1.9.1.",
        "mttr_seconds": 3720, "days_ago": 5,
        "incident_text": "inventory-service memory ratcheting upward under sustained reservation load after v1.9.0. Stock reservation objects created per reservation not returned to pool on expiry — expiry handler cleared the DB record but left the in-memory object retained by a secondary index. Rolled back to v1.8.9 immediately.",
    },

    # ── Error spike incidents (35) ─────────────────────────────────────────────
    {
        "service": "auth-service", "region": "us-west-2",
        "anomaly_type": "error_spike_sudden",
        "root_cause": "Redis session cache became unavailable. Auth fell back to slow DB lookups causing timeouts.",
        "action_taken": "Restarted Redis cluster. Scaled DB connection pool temporarily.",
        "mttr_seconds": 960, "days_ago": 7,
        "incident_text": "auth-service error rate spiked to 28/min after Redis session cache became unavailable. Service fell back to direct database session lookups — DB connection pool exhausted under the increased load, causing timeouts and 500 errors. Redis restarted; error rate recovered within 2 minutes.",
    },
    {
        "service": "payment-service", "region": "us-east-1",
        "anomaly_type": "error_spike_sudden",
        "root_cause": "Downstream payment gateway returning 503 responses under load. Error propagated to checkout flow.",
        "action_taken": "Activated circuit breaker. Routed to backup payment processor.",
        "mttr_seconds": 1440, "days_ago": 12,
        "incident_text": "payment-service error rate climbed to 22/min as downstream payment gateway began returning 503s under peak load. Error propagated directly to checkout callers without circuit breaking. Activated circuit breaker; traffic rerouted to secondary payment processor. Error rate normalised within 3 minutes.",
    },
    {
        "service": "checkout-service", "region": "us-east-1",
        "anomaly_type": "error_spike_sudden",
        "root_cause": "Database connection pool exhausted during flash sale traffic surge. Pool sized for normal load.",
        "action_taken": "Increased pool max connections from 20 to 80. Added read replica.",
        "mttr_seconds": 2100, "days_ago": 18,
        "incident_text": "checkout-service errors spiked to 35/min during flash sale. Database connection pool exhausted — configured for normal load at 20 connections, flash sale traffic 5x normal. New requests queued waiting for connections until timeout. Pool size increased; read replica added for query offload.",
    },
    {
        "service": "auth-service", "region": "us-west-2",
        "anomaly_type": "error_spike_sudden",
        "root_cause": "TLS certificate expired on internal service-to-service authentication endpoint.",
        "action_taken": "Renewed certificate. Restarted affected services.",
        "mttr_seconds": 1200, "days_ago": 25,
        "incident_text": "auth-service 500 error rate spiking across service-to-service calls. Investigation revealed TLS certificate on internal auth endpoint expired at midnight. All service clients failing certificate validation — errors propagated to API layer. Certificate renewed and rotated; services restarted to pick up new cert.",
    },
    {
        "service": "payment-service", "region": "us-east-1",
        "anomaly_type": "error_spike_sudden",
        "root_cause": "DNS resolution failure for external 3D Secure authentication endpoint. Provider DNS TTL not respected by resolver.",
        "action_taken": "Switched to backup DNS resolver. Hardcoded IP as temporary fallback.",
        "mttr_seconds": 900, "days_ago": 30,
        "incident_text": "payment-service 3D Secure authentication failing — error rate jumped to 18/min. DNS resolution for external 3D Secure provider failing: resolver caching stale NXDOMAIN response beyond TTL. All 3D Secure requests failing with connection refused. Backup DNS resolver configured; IP hardcoded as temporary measure.",
    },
    {
        "service": "payment-service", "region": "us-east-1",
        "anomaly_type": "error_spike_sudden",
        "root_cause": "Rate limit hit on third-party payment processor API. Limit not scaled for increased transaction volume.",
        "action_taken": "Upgraded payment processor API tier. Added request queuing and backpressure.",
        "mttr_seconds": 1800, "days_ago": 38,
        "incident_text": "payment-service errors spiking as third-party payment processor returning 429 rate limit responses. Transaction volume grew 40% after marketing campaign but API tier limit unchanged. Processor returning 429 for all requests above limit. Upgraded API tier; implemented request queue with exponential backoff.",
    },
    {
        "service": "checkout-service", "region": "us-east-1",
        "anomaly_type": "error_spike_sudden",
        "root_cause": "Database deadlock on checkout_orders table under high concurrency. Two transactions acquiring row locks in opposite order.",
        "action_taken": "Fixed lock acquisition order. Added deadlock retry logic.",
        "mttr_seconds": 2400, "days_ago": 48,
        "incident_text": "checkout-service error rate spiking with deadlock exceptions. Two code paths acquiring row locks on checkout_orders in opposite order — creating deadlock under concurrency. Transaction A locked row 1 then row 2; Transaction B locked row 2 then row 1. Database killing deadlocked transactions, surfacing as 500 errors. Lock order normalised.",
    },
    {
        "service": "checkout-service", "region": "us-east-1",
        "anomaly_type": "error_spike_sudden",
        "root_cause": "Kafka consumer lag building up, causing order processing timeouts exceeding client patience.",
        "action_taken": "Added 4 consumer replicas. Increased partition count.",
        "mttr_seconds": 3600, "days_ago": 58,
        "incident_text": "checkout-service error rate climbing as Kafka consumer lag grew. Consumer processing orders too slowly — lag building as producers outpaced consumers. Clients timing out waiting for order confirmation. Error rate peaked at 25/min. Added consumer replicas and increased partition count to parallelize processing.",
    },
    {
        "service": "payment-service", "region": "us-east-1",
        "anomaly_type": "error_spike_sudden",
        "root_cause": "Circuit breaker opened prematurely due to timeout threshold set to 100ms — too aggressive for payment gateway latency.",
        "action_taken": "Increased circuit breaker timeout threshold to 2000ms.",
        "mttr_seconds": 480, "days_ago": 68,
        "incident_text": "payment-service circuit breaker opening continuously — error rate spiking as open circuit rejected all payment requests. Circuit breaker timeout configured at 100ms, but payment gateway P99 latency is 400ms. Almost every request triggered the breaker. Timeout threshold corrected to 2000ms; breaker closed; errors resolved immediately.",
    },
    {
        "service": "checkout-service", "region": "us-east-1",
        "anomaly_type": "error_spike_sudden",
        "root_cause": "Order processing message queue full. Producer backpressure blocking checkout API response.",
        "action_taken": "Scaled message queue broker. Added consumer instances.",
        "mttr_seconds": 2880, "days_ago": 75,
        "incident_text": "checkout-service errors as order processing queue reached capacity. Message queue broker at max storage — producers blocked attempting to enqueue new orders. Checkout API responses delayed until timeout, surfacing as 500 errors to customers. Queue broker scaled; additional consumers added to drain queue.",
    },
    {
        "service": "auth-service", "region": "us-west-2",
        "anomaly_type": "error_spike_sudden",
        "root_cause": "Network partition between auth-service pods and Redis cluster. Redis unreachable for 4 minutes.",
        "action_taken": "Recovered network connectivity. Auth-service reconnected automatically.",
        "mttr_seconds": 540, "days_ago": 82,
        "incident_text": "auth-service error rate surging — Redis cluster unreachable due to transient network partition. All session lookups failing; auth-service unable to validate sessions. Error rate peaked at 32/min. Network connectivity restored after 4 minutes; auth-service reconnected to Redis automatically and error rate dropped.",
    },
    {
        "service": "payment-service", "region": "us-east-1",
        "anomaly_type": "error_spike_sudden",
        "root_cause": "Connection reset by payment gateway on TLS renegotiation. Gateway dropped connections mid-request during maintenance.",
        "action_taken": "Added retry logic for connection reset errors. Gateway maintenance window confirmed.",
        "mttr_seconds": 900, "days_ago": 90,
        "incident_text": "payment-service error spike: connection reset errors from payment gateway. Gateway performing maintenance that involved TLS certificate rotation — existing connections forcibly reset mid-request. Retry logic not implemented for this error type. Error rate peaked at 15/min during 15-minute maintenance window. Retry added post-incident.",
    },
    {
        "service": "auth-service", "region": "us-west-2",
        "anomaly_type": "error_spike_sudden",
        "root_cause": "Token validation microservice returning 500s after database schema migration left index missing.",
        "action_taken": "Rebuilt missing index. Token validation recovered.",
        "mttr_seconds": 1680, "days_ago": 98,
        "incident_text": "auth-service token validation failing — downstream token validator returning 500 errors. Database migration script dropped and recreated the tokens table but migration for index creation failed silently. Token lookup queries performing full table scan then timing out. Missing index rebuilt; validation recovered.",
    },
    {
        "service": "checkout-service", "region": "us-east-1",
        "anomaly_type": "error_spike_sudden",
        "root_cause": "Inventory stock check service timing out. Inventory DB under heavy load from batch recount job running concurrently.",
        "action_taken": "Rescheduled batch job to off-peak. Added read replica for real-time queries.",
        "mttr_seconds": 2160, "days_ago": 107,
        "incident_text": "checkout-service inventory check timeouts causing 500 errors. Inventory service DB under contention — nightly batch recount job scheduled during peak checkout hours. Real-time stock queries competing with batch job for DB resources. Checkout errors peaked at 20/min. Batch job rescheduled to 2am; read replica added.",
    },
    {
        "service": "auth-service", "region": "us-west-2",
        "anomaly_type": "error_spike_sudden",
        "root_cause": "Redis cluster failover caused 90-second unavailability window during leader election.",
        "action_taken": "Auth-service reconnected after Redis elected new primary. No action required.",
        "mttr_seconds": 120, "days_ago": 113,
        "incident_text": "auth-service error spike lasting 90 seconds. Redis cluster leader election triggered after primary node became unresponsive. During election, Redis rejected all writes. Auth-service session writes failing. Error rate peaked at 40/min for 90 seconds then dropped as new Redis primary elected and connections re-established.",
    },
    {
        "service": "inventory-service", "region": "eu-west-1",
        "anomaly_type": "error_spike_sudden",
        "root_cause": "Database read replica lag exceeded 30 seconds during high write load. Stale reads causing stock level inconsistencies and validation errors.",
        "action_taken": "Rerouted real-time reads to primary. Investigated replica lag.",
        "mttr_seconds": 1440, "days_ago": 120,
        "incident_text": "inventory-service validation errors spiking as read replica falling behind primary by 30 seconds. Stock reservation writes going to primary, reads going to lagging replica — resulting in phantom stock availability. Validation checks catching inconsistency and returning errors. Real-time reads rerouted to primary temporarily.",
    },
    {
        "service": "checkout-service", "region": "us-east-1",
        "anomaly_type": "error_spike_sudden",
        "root_cause": "Load balancer health check misconfigured — marking healthy instances as unhealthy, removing them from rotation.",
        "action_taken": "Corrected health check path. Restored instances to rotation.",
        "mttr_seconds": 1080, "days_ago": 127,
        "incident_text": "checkout-service error rate spiking as traffic concentrated on fewer instances. Load balancer health check path changed from /health to /status by new deployment but LB config not updated. Healthy instances marked unhealthy and removed from rotation — remaining instances overloaded. Health check path corrected.",
    },
    {
        "service": "payment-service", "region": "us-east-1",
        "anomaly_type": "error_spike_sudden",
        "root_cause": "Surge in webhook delivery callbacks overwhelming payment processor's async handler thread pool.",
        "action_taken": "Added webhook queue and async processing. Increased handler thread pool.",
        "mttr_seconds": 2520, "days_ago": 136,
        "incident_text": "payment-service error rate climbing as webhook callback surge overwhelmed async handler thread pool. External partner began sending webhook events at 10x normal rate after their system recovered from an outage. Thread pool exhausted; new webhooks rejected with 503. Webhook queue added; thread pool scaled.",
    },
    {
        "service": "checkout-service", "region": "us-east-1",
        "anomaly_type": "error_spike_sudden",
        "root_cause": "Bot traffic sending malformed cart requests causing unhandled exceptions in checkout validator.",
        "action_taken": "Added input validation for malformed cart payload. Bot IPs rate-limited.",
        "mttr_seconds": 1920, "days_ago": 143,
        "incident_text": "checkout-service error rate spiking. Bot traffic submitting malformed cart payloads with null required fields. Cart validator throwing NullPointerException on malformed input — unhandled, surfacing as 500. Bot IPs identified and rate-limited. Input validation hardened to return 400 on malformed payload rather than throwing.",
    },
    {
        "service": "auth-service", "region": "us-west-2",
        "anomaly_type": "error_spike_sudden",
        "root_cause": "Session store evicting active sessions under memory pressure. Evicted sessions causing 401 errors on valid requests.",
        "action_taken": "Restarted auth-redis to clear leaked memory. Increased Redis memory allocation.",
        "mttr_seconds": 1560, "days_ago": 150,
        "incident_text": "auth-service returning 401 errors on valid sessions. Redis session store running out of memory — eviction policy set to allkeys-lru, evicting active sessions to make room for new ones. Users experiencing intermittent logouts. Auth-redis restarted to clear memory leak; Redis memory limit increased.",
    },
    {
        "service": "payment-service", "region": "us-east-1",
        "anomaly_type": "error_spike_sudden",
        "root_cause": "Outbound HTTP connection pool to fraud detection API exhausted. Pool max set to 5 — far too low.",
        "action_taken": "Increased fraud API connection pool to 50. Restarted payment service.",
        "mttr_seconds": 720, "days_ago": 158,
        "incident_text": "payment-service fraud check timeouts. Outbound HTTP connection pool to fraud detection API set to 5 connections — insufficient for current transaction volume. Requests queued waiting for connection; timeouts surfacing as payment errors. Connection pool increased to 50; payment service restarted to flush queued requests.",
    },
    {
        "service": "inventory-service", "region": "eu-west-1",
        "anomaly_type": "error_spike_sudden",
        "root_cause": "Elasticsearch stock search query timing out under high cardinality query with unbounded aggregation.",
        "action_taken": "Added aggregation size limit. Optimised query with filter first.",
        "mttr_seconds": 2040, "days_ago": 165,
        "incident_text": "inventory-service Elasticsearch stock search timeouts. Search query performing unbounded aggregation on high-cardinality product_id field — query scanning millions of documents. Query time exceeding 30s timeout under load. Filter-first query rewrite and aggregation size limit applied; query time dropped to under 200ms.",
    },
    {
        "service": "auth-service", "region": "us-west-2",
        "anomaly_type": "error_spike_sudden",
        "root_cause": "gRPC keepalive timeout too aggressive — connections dropped during normal processing pauses.",
        "action_taken": "Increased gRPC keepalive timeout from 1s to 20s.",
        "mttr_seconds": 600, "days_ago": 172,
        "incident_text": "auth-service gRPC calls failing with connection reset errors. Keepalive timeout configured at 1 second — any processing pause longer than 1s caused the connection to be closed by the server. Under normal GC pauses, connections dropped. All gRPC callers experiencing intermittent failures. Keepalive timeout increased to 20 seconds.",
    },
    {
        "service": "auth-service", "region": "us-west-2",
        "anomaly_type": "error_spike_sudden",
        "root_cause": "Redis keyspace notification volume overwhelming notification subscriber — subscriber falling behind, causing event processing errors.",
        "action_taken": "Added notification batching and increased subscriber thread pool.",
        "mttr_seconds": 1800, "days_ago": 178,
        "incident_text": "auth-service error spike from Redis keyspace notification overflow. Notification subscriber thread falling behind during session expiry burst — unprocessed events queued in Redis beyond buffer capacity. Subscriber dropping events and logging errors. Notification processing batched; subscriber thread pool scaled to handle burst volume.",
    },
    {
        "service": "auth-service", "region": "us-west-2",
        "anomaly_type": "error_spike_sudden",
        "root_cause": "JWT key rotation caused temporary validation failures. New key propagated to some instances before others.",
        "action_taken": "Implemented key overlap window during rotation. All instances restarted.",
        "mttr_seconds": 840, "days_ago": 3,
        "incident_text": "auth-service JWT validation errors spiking during planned key rotation. New signing key pushed to some pods but not all — tokens signed by new key rejected by pods still using old key. Error rate peaked at 25/min for 5 minutes during partial rotation. Key overlap window added to rotation procedure; all pods restarted simultaneously in future.",
    },
    {
        "service": "checkout-service", "region": "us-east-1",
        "anomaly_type": "error_spike_sudden",
        "root_cause": "Cascading timeout from slow database query. One slow query blocked the connection pool, delaying all checkout operations.",
        "action_taken": "Added query timeout of 5s. Killed long-running query. Pool cleared.",
        "mttr_seconds": 1080, "days_ago": 8,
        "incident_text": "checkout-service errors cascading from a single slow database query. Query on checkout_orders with missing WHERE clause performing full table scan — holding DB connection for 45 seconds. Other requests queuing for connections; pool exhausted. Query timeout added; long-running query killed; pool recovered within 2 minutes.",
    },
    {
        "service": "payment-service", "region": "us-east-1",
        "anomaly_type": "error_spike_sudden",
        "root_cause": "HTTP/2 flow control window exhaustion causing stream stalls on payment confirmation endpoint.",
        "action_taken": "Tuned HTTP/2 flow control window size. Restarted payment gateway connections.",
        "mttr_seconds": 1440, "days_ago": 15,
        "incident_text": "payment-service confirmation endpoint stalling under load. HTTP/2 flow control window exhausted — server not consuming response fast enough, causing streams to stall. Payment confirmations hanging until timeout. Flow control window size increased; existing connections to payment gateway closed and reopened with new settings.",
    },
    {
        "service": "auth-service", "region": "us-west-2",
        "anomaly_type": "error_spike_sudden",
        "root_cause": "CDN origin pull overwhelming auth backend. CDN cache miss storm after configuration pushed with Cache-Control: no-cache.",
        "action_taken": "Reverted CDN cache config. Traffic normalised as cache repopulated.",
        "mttr_seconds": 1200, "days_ago": 22,
        "incident_text": "auth-service overloaded by CDN origin pull storm. CDN cache configuration accidentally changed to Cache-Control: no-cache — every CDN edge node pulling fresh from origin on each request. Auth backend receiving 50x normal traffic. Error rate spiked as auth servers saturated. CDN config reverted; cache repopulated within 20 minutes.",
    },
    {
        "service": "checkout-service", "region": "us-east-1",
        "anomaly_type": "error_spike_sudden",
        "root_cause": "Internal checkout-to-inventory API rate limiting misconfigured at 10 req/s — far below actual usage.",
        "action_taken": "Increased internal rate limit to 500 req/s.",
        "mttr_seconds": 360, "days_ago": 32,
        "incident_text": "checkout-service inventory lookup errors spiking. Internal rate limiter on checkout-to-inventory API calls set to 10 req/s — misconfigured during security hardening. Checkout service making 200 req/s at normal load; 95% of requests rate-limited with 429. Rate limit increased to 500 req/s; errors cleared immediately.",
    },
    {
        "service": "auth-service", "region": "us-west-2",
        "anomaly_type": "error_spike_sudden",
        "root_cause": "Redis SLOWLOG entries blocking main thread. Large key deletion blocking Redis event loop for 800ms intervals.",
        "action_taken": "Used UNLINK instead of DEL for large keys. Cleared accumulated large keys.",
        "mttr_seconds": 900, "days_ago": 43,
        "incident_text": "auth-service intermittent error spikes every few minutes. Redis main thread blocking for 800ms when large session dump key deleted with DEL command. During block, all Redis operations stalled. Auth-service session operations timing out during block intervals. Switched to async UNLINK command for large key deletion.",
    },
    {
        "service": "payment-service", "region": "us-east-1",
        "anomaly_type": "error_spike_sudden",
        "root_cause": "Database connection string changed during secrets rotation but payment service not redeployed to pick up new credentials.",
        "action_taken": "Redeployed payment service with updated credentials.",
        "mttr_seconds": 540, "days_ago": 53,
        "incident_text": "payment-service database connection failing after secrets rotation. New database credentials pushed to secrets manager but payment service not restarted — still using cached old credentials. DB authentication failing for all new connections. Existing connections in pool kept working until they expired. Service redeployed with new credentials.",
    },
    {
        "service": "inventory-service", "region": "eu-west-1",
        "anomaly_type": "error_spike_sudden",
        "root_cause": "Downstream supplier API returning empty JSON responses (200 OK, empty body). Inventory service not handling empty body, throwing parse error.",
        "action_taken": "Added null check for empty API response. Supplier contacted.",
        "mttr_seconds": 2400, "days_ago": 63,
        "incident_text": "inventory-service supplier feed errors spiking. External supplier API returning 200 OK with empty body during their maintenance window. Inventory service attempted to parse empty JSON, throwing NullPointerException. Error rate peaked at 18/min. Empty response handling added; supplier contacted about API behaviour during maintenance.",
    },
    {
        "service": "checkout-service", "region": "us-east-1",
        "anomaly_type": "error_spike_sudden",
        "root_cause": "Thread pool saturation in async order event handler. Events backed up faster than processing.",
        "action_taken": "Increased event handler thread pool from 4 to 20. Added event queue.",
        "mttr_seconds": 1680, "days_ago": 73,
        "incident_text": "checkout-service order event processing errors. Async event handler thread pool at 4 threads — event burst from marketing campaign generated 50 events/second. Pool saturated; events backed up; handler throwing RejectedExecutionException. Error rate climbed as rejections surfaced to callers. Thread pool scaled; buffered queue added.",
    },
    {
        "service": "inventory-service", "region": "eu-west-1",
        "anomaly_type": "error_spike_sudden",
        "root_cause": "Network MTU mismatch causing packet fragmentation and retransmissions on inventory service pod network.",
        "action_taken": "Corrected MTU configuration. Network retransmissions dropped to zero.",
        "mttr_seconds": 1920, "days_ago": 83,
        "incident_text": "inventory-service latency and error spikes caused by excessive TCP retransmissions. Network MTU misconfigured after cluster upgrade — packets fragmented at network boundary. Fragmented packets causing retransmission storms. TCP connection timeouts surfacing as application errors. MTU configuration corrected on pod network; retransmissions resolved.",
    },
    {
        "service": "payment-service", "region": "us-east-1",
        "anomaly_type": "error_spike_sudden",
        "root_cause": "Surge in bot traffic sending payment probe requests causing 429s to cascade into downstream error handlers.",
        "action_taken": "Applied WAF rate limiting rule. Bot traffic dropped 95%. Error rate normalised.",
        "mttr_seconds": 1380, "days_ago": 93,
        "incident_text": "payment-service error rate spiking due to bot traffic surge probing payment endpoints. Bots sending payment initiation requests at high frequency — rate limiter returning 429s which error handlers logged as failures. Legitimate users affected by latency. WAF rule applied to rate-limit bot user agents; error rate returned to baseline.",
    },

    # ── Deployment regression incidents (30) ───────────────────────────────────
    {
        "service": "checkout-service", "region": "us-east-1",
        "anomaly_type": "deployment_regression",
        "root_cause": "Deploy v3.4.2 introduced unhandled NPE in cart serialisation. CartItem.price field made nullable without null handling.",
        "action_taken": "Immediate rollback to v3.4.1.",
        "mttr_seconds": 480, "days_ago": 3,
        "incident_text": "checkout-service error rate spiked immediately after v3.4.2 deployment. CartItem.price field changed to nullable but serialisation code not updated to handle null — NullPointerException on any cart containing a promotional item with null price. Immediate rollback to v3.4.1; error rate cleared within 1 minute.",
    },
    {
        "service": "payment-service", "region": "us-east-1",
        "anomaly_type": "deployment_regression",
        "root_cause": "Missing null check in payment amount formatter introduced by v2.2.0. Null currency code throws NPE.",
        "action_taken": "Hotfix v2.2.1 deployed with null guard.",
        "mttr_seconds": 720, "days_ago": 9,
        "incident_text": "payment-service NPE errors after v2.2.0 deployment. Payment amount formatter refactored to use currency code — null check missing. Any transaction with missing currency code (legacy data) throwing NullPointerException in payment processing. Hotfix v2.2.1 deployed with null guard; legacy data backfill queued.",
    },
    {
        "service": "auth-service", "region": "us-west-2",
        "anomaly_type": "deployment_regression",
        "root_cause": "Dependency version bump (jackson-databind 2.13 → 2.14) changed deserialization strictness, breaking auth token parsing.",
        "action_taken": "Pinned jackson-databind to 2.13. Rolled back auth-service.",
        "mttr_seconds": 1080, "days_ago": 16,
        "incident_text": "auth-service token parsing failures after dependency bump. jackson-databind 2.14 introduced stricter deserialization — existing auth tokens with extra unknown fields no longer accepted. All existing tokens invalid. Rolled back to jackson 2.13; configured 2.14 with FAIL_ON_UNKNOWN_PROPERTIES=false for future upgrade.",
    },
    {
        "service": "inventory-service", "region": "eu-west-1",
        "anomaly_type": "deployment_regression",
        "root_cause": "Config change removed database connection retry logic. No retry on transient connection failures.",
        "action_taken": "Restored retry configuration. Redeployed.",
        "mttr_seconds": 900, "days_ago": 23,
        "incident_text": "inventory-service errors spiking on transient database connection failures. Config refactor accidentally removed retry block from DB connection initialization. Transient failures previously retried 3 times now surfaced immediately as errors. Retry configuration restored; service redeployed. Error rate returned to baseline.",
    },
    {
        "service": "checkout-service", "region": "us-east-1",
        "anomaly_type": "deployment_regression",
        "root_cause": "Feature flag for new checkout flow inadvertently enabled in production. New flow missing edge case handling.",
        "action_taken": "Disabled feature flag. Rolled back to old checkout flow.",
        "mttr_seconds": 600, "days_ago": 29,
        "incident_text": "checkout-service errors after feature flag incorrectly enabled. New checkout flow activated in production but missing handling for guest checkout edge case — NPE on guest carts. Feature flag disabled immediately; old flow restored. New flow requires guest checkout support before re-enabling.",
    },
    {
        "service": "checkout-service", "region": "us-east-1",
        "anomaly_type": "deployment_regression",
        "root_cause": "Bad database migration on checkout_orders table. Column renamed without backward-compatible alias. Old queries breaking.",
        "action_taken": "Rolled back migration. Added column alias in v3.6.1.",
        "mttr_seconds": 1320, "days_ago": 36,
        "incident_text": "checkout-service errors after database migration. Column renamed from total_price to order_total — old queries using total_price failing with column not found. Migration deployed ahead of application change. Rolled back migration immediately; coordinated migration and code change deployed together in v3.6.1.",
    },
    {
        "service": "payment-service", "region": "us-east-1",
        "anomaly_type": "deployment_regression",
        "root_cause": "API version mismatch during rolling deployment. New pods expecting v2 request format; old pods sending v1. Intermittent failures.",
        "action_taken": "Completed rolling deployment quickly. Added version negotiation for future.",
        "mttr_seconds": 840, "days_ago": 44,
        "incident_text": "payment-service intermittent errors during rolling deployment. New pods deployed expecting updated request payload format — old pods still sending v1 format. Load balancer routing to both old and new pods; approximately 50% of requests failing. Rolled out remaining new pods quickly to complete deployment. API version negotiation added.",
    },
    {
        "service": "auth-service", "region": "us-west-2",
        "anomaly_type": "deployment_regression",
        "root_cause": "Logger format change broke structured logging parser. JSON log format changed, alerting pipeline consuming malformed output.",
        "action_taken": "Reverted logger config. Updated parser to handle new format.",
        "mttr_seconds": 960, "days_ago": 49,
        "incident_text": "auth-service structured log parsing failures after logger config change. Log format changed from flat JSON to nested JSON — downstream log parser expecting flat format. Error in log pipeline causing false alerts and monitoring gaps. Logger config reverted; parser updated to handle both formats before next deploy.",
    },
    {
        "service": "inventory-service", "region": "eu-west-1",
        "anomaly_type": "deployment_regression",
        "root_cause": "Timeout configuration reduced from 30s to 3s for supplier API calls during refactor.",
        "action_taken": "Restored timeout to 30s. Redeployed inventory-service.",
        "mttr_seconds": 720, "days_ago": 54,
        "incident_text": "inventory-service supplier API timeouts after config change. Timeout value for external supplier API calls reduced from 30s to 3s during performance refactor. Supplier API P99 latency is 8s — 95% of requests now timing out. Timeout restored to 30s; service redeployed. Future timeout changes require supplier API SLA review.",
    },
    {
        "service": "checkout-service", "region": "us-east-1",
        "anomaly_type": "deployment_regression",
        "root_cause": "Schema migration left orphaned foreign key constraint referencing dropped table.",
        "action_taken": "Dropped orphaned FK constraint manually. Migrated cleanly.",
        "mttr_seconds": 1440, "days_ago": 61,
        "incident_text": "checkout-service order inserts failing after schema migration. Migration dropped legacy table but left foreign key constraint referencing it — subsequent insert attempts failed with FK violation. Error rate spiked on all new orders. Orphaned FK constraint manually dropped; migration amended to remove constraint before dropping table.",
    },
    {
        "service": "payment-service", "region": "us-east-1",
        "anomaly_type": "deployment_regression",
        "root_cause": "Guava version upgrade changed MurmurHash3 implementation. Sharding keys producing different distribution, routing requests to wrong shards.",
        "action_taken": "Pinned Guava version. Added shard key stability test.",
        "mttr_seconds": 1800, "days_ago": 69,
        "incident_text": "payment-service request routing errors after Guava upgrade. MurmurHash3 implementation changed in new Guava version — existing shard keys hashed differently, routing payment requests to wrong payment processor shards. Cross-shard requests failing authentication. Guava version pinned; shard key stability regression test added.",
    },
    {
        "service": "auth-service", "region": "us-west-2",
        "anomaly_type": "deployment_regression",
        "root_cause": "Spring Boot autoconfiguration conflict with custom DataSource bean after Spring Boot version upgrade.",
        "action_taken": "Excluded conflicting autoconfiguration. Redeployed.",
        "mttr_seconds": 1200, "days_ago": 78,
        "incident_text": "auth-service database connections failing after Spring Boot upgrade. New version auto-configuring DataSource conflicting with custom DataSource bean — two DataSources initialising, one without correct credentials. Auth DB connections intermittently using wrong DataSource. Excluded conflicting autoconfiguration; custom bean used exclusively.",
    },
    {
        "service": "inventory-service", "region": "eu-west-1",
        "anomaly_type": "deployment_regression",
        "root_cause": "Environment variable for supplier API endpoint missing in production deploy. Service falling back to localhost.",
        "action_taken": "Added missing env var. Redeployed service.",
        "mttr_seconds": 840, "days_ago": 86,
        "incident_text": "inventory-service supplier sync failing after deployment. Environment variable SUPPLIER_API_URL not added to production config — service defaulting to localhost:8080. All supplier API calls failing with connection refused. Missing variable identified from log output. Env var added to production config; service redeployed.",
    },
    {
        "service": "payment-service", "region": "us-east-1",
        "anomaly_type": "deployment_regression",
        "root_cause": "Jackson deserialization strictness changed — FAIL_ON_UNKNOWN_PROPERTIES enabled globally, breaking existing API contract.",
        "action_taken": "Disabled FAIL_ON_UNKNOWN_PROPERTIES globally. Redeployed.",
        "mttr_seconds": 1080, "days_ago": 94,
        "incident_text": "payment-service rejecting valid requests after Jackson config change. Global deserialization config changed to fail on unknown properties — external payment partners adding new optional fields to callbacks. All callbacks with new fields rejected with 400. Config reverted; per-class annotations used for strict models only.",
    },
    {
        "service": "checkout-service", "region": "us-east-1",
        "anomaly_type": "deployment_regression",
        "root_cause": "Async order processing thread pool size reduced from 20 to 2 during performance refactor.",
        "action_taken": "Restored thread pool to 20. Redeployed.",
        "mttr_seconds": 660, "days_ago": 102,
        "incident_text": "checkout-service order processing queue backing up after config change. Async processing thread pool reduced to 2 threads during performance tuning — intended for a different service. Order processing throughput dropped 90%; queue backing up. Thread pool size corrected to 20; service redeployed.",
    },
    {
        "service": "auth-service", "region": "us-west-2",
        "anomaly_type": "deployment_regression",
        "root_cause": "Metrics exporter port conflict after new sidecar added. Sidecar binding to same port as auth-service metrics.",
        "action_taken": "Changed sidecar metrics port. Redeployed auth pods.",
        "mttr_seconds": 720, "days_ago": 110,
        "incident_text": "auth-service pods failing to start cleanly after sidecar added. Monitoring sidecar binding to port 9090 — same as auth-service Prometheus metrics exporter. Port conflict causing one of the two processes to fail. Auth pods in crash loop on some nodes. Sidecar metrics port changed to 9091; pods redeployed successfully.",
    },
    {
        "service": "inventory-service", "region": "eu-west-1",
        "anomaly_type": "deployment_regression",
        "root_cause": "TLS version downgrade in HTTP client library upgrade. Client now negotiating TLS 1.0 with supplier; supplier deprecated TLS 1.0.",
        "action_taken": "Configured TLS minimum to 1.2 in client. Redeployed.",
        "mttr_seconds": 1560, "days_ago": 117,
        "incident_text": "inventory-service supplier connections failing after HTTP client library upgrade. New client library defaulting to TLS 1.0 for compatibility — supplier API deprecated TLS 1.0 and returning handshake failure. All supplier sync requests failing. TLS minimum version set to 1.2 in client config; service redeployed.",
    },
    {
        "service": "payment-service", "region": "us-east-1",
        "anomaly_type": "deployment_regression",
        "root_cause": "Async error handler removed during cleanup branch merge. Unhandled async exceptions now crashing payment processing threads.",
        "action_taken": "Restored async error handler. Hotfix deployed.",
        "mttr_seconds": 900, "days_ago": 124,
        "incident_text": "payment-service processing threads crashing. Async error handler accidentally removed during branch cleanup — uncaught exceptions in async payment processing killing threads. Thread pool slowly depleted; payment throughput dropping. Hotfix restored async error handler; thread pool recovered after restart.",
    },
    {
        "service": "checkout-service", "region": "us-east-1",
        "anomaly_type": "deployment_regression",
        "root_cause": "Internal rate limiting added to checkout-to-payment API without coordinating with payment team. Limit too low for production traffic.",
        "action_taken": "Increased rate limit. Coordinated limits across teams.",
        "mttr_seconds": 600, "days_ago": 132,
        "incident_text": "checkout-service payment API rate limit errors after security hardening. Internal rate limit added to checkout→payment calls — limit set at 10 req/s based on staging traffic, but production is 200 req/s. 95% of payment requests rate-limited with 429. Rate limit raised to 500 req/s; cross-team traffic validation added to release checklist.",
    },
    {
        "service": "auth-service", "region": "us-west-2",
        "anomaly_type": "deployment_regression",
        "root_cause": "Content-Type header validation strictened in API gateway. Clients sending application/json with charset rejected.",
        "action_taken": "Relaxed Content-Type validation to accept charset variants.",
        "mttr_seconds": 1200, "days_ago": 139,
        "incident_text": "auth-service API rejecting requests from mobile clients after API gateway update. Content-Type validation strictened to require exact 'application/json' — mobile SDK sending 'application/json; charset=utf-8'. All mobile auth requests returning 415 Unsupported Media Type. Gateway validation relaxed to accept charset variants.",
    },
    {
        "service": "inventory-service", "region": "eu-west-1",
        "anomaly_type": "deployment_regression",
        "root_cause": "Circuit breaker threshold changed to 0 in config migration. Circuit breaking on first error, staying open.",
        "action_taken": "Corrected circuit breaker threshold to 50%. Redeployed.",
        "mttr_seconds": 480, "days_ago": 147,
        "incident_text": "inventory-service circuit breaker in permanent open state after config migration. Error rate threshold migrated as integer 0 instead of percentage 50 — circuit breaker opening on the first error and staying open. All downstream supplier calls rejected by open circuit. Threshold corrected; circuit closed; service recovered immediately.",
    },
    {
        "service": "payment-service", "region": "us-east-1",
        "anomaly_type": "deployment_regression",
        "root_cause": "Input validation regex too strict — valid international payment amounts with comma decimal separator rejected.",
        "action_taken": "Updated validation regex to accept both . and , as decimal separators.",
        "mttr_seconds": 960, "days_ago": 153,
        "incident_text": "payment-service rejecting valid international payment amounts after validation tightening. New regex validating amount format required period as decimal separator — international customers using comma separator (e.g. '12,50' for 12.50) rejected with 400. Validation updated to accept both formats; previously rejected payments reprocessed.",
    },
    {
        "service": "auth-service", "region": "us-west-2",
        "anomaly_type": "deployment_regression",
        "root_cause": "Cookie SameSite policy changed to Strict, breaking OAuth callback in mobile app WebView.",
        "action_taken": "Changed SameSite to Lax for auth cookies. Redeployed.",
        "mttr_seconds": 1440, "days_ago": 161,
        "incident_text": "auth-service mobile OAuth logins failing after cookie policy change. SameSite attribute changed to Strict for auth cookies — OAuth callback from external provider in mobile WebView losing auth cookie on redirect. Users stuck in OAuth loop, unable to authenticate on mobile. SameSite changed to Lax; mobile auth restored.",
    },
    {
        "service": "inventory-service", "region": "eu-west-1",
        "anomaly_type": "deployment_regression",
        "root_cause": "Lazy loading changed to eager on large product object graph. Startup loading entire product catalogue into memory.",
        "action_taken": "Reverted to lazy loading. Service startup time reduced.",
        "mttr_seconds": 1200, "days_ago": 169,
        "incident_text": "inventory-service OOM on startup after configuration change. Product object graph loading changed from lazy to eager — entire product catalogue loaded at startup. With 500k products, startup consumed 12GB of heap, triggering OOM kill before service became ready. Lazy loading restored; startup time reduced from 8 minutes to 30 seconds.",
    },
    {
        "service": "payment-service", "region": "us-east-1",
        "anomaly_type": "deployment_regression",
        "root_cause": "Connection pool min-size reduced to 0 during performance tuning. Cold start on first payment of each period caused pool exhaustion.",
        "action_taken": "Set min pool size to 10. Redeployed.",
        "mttr_seconds": 540, "days_ago": 6,
        "incident_text": "payment-service intermittent timeouts at start of each business period. DB connection pool min-size set to 0 — no connections pre-established. First payment burst each morning exhausted pool as connections were created on-demand. Under load, new connection creation slower than request arrival. Min pool size set to 10; pre-warming connections on startup.",
    },
    {
        "service": "checkout-service", "region": "us-east-1",
        "anomaly_type": "deployment_regression",
        "root_cause": "Cache TTL accidentally set to 0 seconds in product pricing cache. Cache misses on every request.",
        "action_taken": "Set TTL to 300s. Redeployed checkout-service.",
        "mttr_seconds": 480, "days_ago": 11,
        "incident_text": "checkout-service database overloaded after product pricing cache disabled. Cache TTL set to 0 seconds in config — effectively disabling the cache. Every pricing request going to the database. DB CPU spiked to 95%; query latency degraded; checkout error rate rising. TTL corrected to 300 seconds; DB load normalised immediately.",
    },
    {
        "service": "auth-service", "region": "us-west-2",
        "anomaly_type": "deployment_regression",
        "root_cause": "Validation schema changed, rejecting valid auth tokens issued by previous version. Token format had optional fields that new schema requires.",
        "action_taken": "Made new fields optional in schema. Redeployed.",
        "mttr_seconds": 960, "days_ago": 19,
        "incident_text": "auth-service rejecting previously valid tokens after schema update. New validation schema required two additional fields that old token issuer did not include — all existing tokens invalid until naturally replaced. Error rate climbed as active sessions expired and re-authenticated. Schema updated to make new fields optional with defaults.",
    },
    {
        "service": "inventory-service", "region": "eu-west-1",
        "anomaly_type": "deployment_regression",
        "root_cause": "Database cursor not closed in new batch query path. Connection leak under sustained load.",
        "action_taken": "Added cursor close in finally block. Hotfix deployed.",
        "mttr_seconds": 1080, "days_ago": 26,
        "incident_text": "inventory-service database connection pool exhaustion after new batch query feature deployed. New code path not closing database cursor in finally block — cursors leaking connections from pool. Pool exhausted within 2 hours of deployment. Hotfix added cursor close to finally block; service redeployed.",
    },
    {
        "service": "payment-service", "region": "us-east-1",
        "anomaly_type": "deployment_regression",
        "root_cause": "Serialisation format changed from JSON to MessagePack without backward compatibility. Callers sending JSON receiving parse errors.",
        "action_taken": "Rollback to JSON format. Planned coordinated migration.",
        "mttr_seconds": 720, "days_ago": 33,
        "incident_text": "payment-service parse errors after serialisation format migration. Internal format changed to MessagePack for performance but calling services not updated simultaneously. Callers sending JSON receiving MessagePack parse failures. Rollback to JSON format immediately; migration rescheduled with coordinated caller update.",
    },
    {
        "service": "checkout-service", "region": "us-east-1",
        "anomaly_type": "deployment_regression",
        "root_cause": "Environment variable for external payment API key missing in new deployment environment. All payment API calls failing authentication.",
        "action_taken": "Added missing API key env var. Redeployed.",
        "mttr_seconds": 840, "days_ago": 41,
        "incident_text": "checkout-service payment initiation failing after deployment to new environment. PAYMENT_API_KEY environment variable not included in new environment config — all payment API calls returning 401 Unauthorized. Error rate spiked to 35/min. Missing variable identified from error logs; added to environment config; service redeployed.",
    },
]


def _stream_loop(es, stop_event: threading.Event):
    while not stop_event.is_set():
        now = datetime.now(timezone.utc)
        diurnal = math.sin(math.pi * (now.hour + now.minute / 60) / 12)
        docs = []
        for svc in SERVICES:
            for metric, cfg in BASELINES.items():
                v = random.gauss(cfg["mean"] + diurnal * cfg["std"] * 0.5, cfg["std"])
                v = max(5, min(95, v)) if metric in ("memory_percent", "cpu_percent") else max(0, min(5, v))
                docs.append({
                    "@timestamp": now.isoformat(), "service": svc["name"],
                    "region": svc["region"], "metric_type": metric,
                    "value": round(v, 2), "unit": METRIC_UNITS[metric],
                })
        try:
            es.bulk(operations=[op for d in docs for op in [{"index": {"_index": "metrics-quantumstate"}}, d]])
        except Exception:
            pass
        stop_event.wait(30)


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/status")
def get_status():
    global _stream_thread
    with _stream_lock:
        streaming = _stream_thread is not None and _stream_thread.is_alive()
    es = get_es()
    indices = {}
    for name in QUANTUMSTATE_INDICES:
        try:
            exists = es.indices.exists(index=name)
            count = es.count(index=name)["count"] if exists else 0
            indices[name] = {"exists": bool(exists), "count": count}
        except Exception:
            indices[name] = {"exists": False, "count": 0}
    return {"streaming": streaming, "indices": indices}


@router.post("/setup")
def run_setup():
    from elasticsearch import helpers

    es = get_es()

    def clamp(v, lo, hi): return max(lo, min(hi, v))

    # Create indices (skip if already exists; warn if creation fails e.g. ELSER not deployed)
    for name, body in QUANTUMSTATE_INDICES.items():
        if not es.indices.exists(index=name):
            try:
                es.indices.create(index=name, body=body)
            except Exception as exc:
                # Most likely cause: ELSER inference endpoint not deployed yet.
                # Run: python elastic-setup/setup_elser.py  then retry.
                print(f"[sim/setup] Warning: could not create {name}: {exc}")
        else:
            # Index exists — try to add incident_text mapping if not already present
            # (idempotent; safe to call on existing indices)
            if name == "incidents-quantumstate":
                try:
                    es.indices.put_mapping(
                        index=name,
                        body={"properties": {
                            "incident_text": {
                                "type":         "semantic_text",
                                "inference_id": ".elser-2-elasticsearch",
                            }
                        }},
                    )
                except Exception:
                    pass  # ELSER not deployed or field already exists — either is fine

    # 24h baseline metrics
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=24)
    docs, t = [], start
    while t <= now:
        for svc in SERVICES:
            diurnal = math.sin(math.pi * (t.hour + t.minute / 60) / 12)
            for metric, cfg in BASELINES.items():
                v = random.gauss(cfg["mean"] + diurnal * cfg["std"] * 0.5, cfg["std"])
                if metric in ("memory_percent", "cpu_percent"):
                    v = clamp(v, 5, 95)
                elif metric == "error_rate":
                    v = clamp(v, 0, 5)
                elif metric == "latency_ms":
                    v = clamp(v, 10, 2000)
                else:
                    v = clamp(v, 0, 5000)
                docs.append({"_index": "metrics-quantumstate", "_source": {
                    "@timestamp": t.isoformat(), "service": svc["name"],
                    "region": svc["region"], "metric_type": metric,
                    "value": round(v, 2), "unit": METRIC_UNITS[metric],
                }})
        t += timedelta(minutes=1)

    for _ in helpers.parallel_bulk(es, docs, chunk_size=2000, thread_count=4,
                                   raise_on_error=False, raise_on_exception=False):
        pass

    # Baseline logs
    log_docs, t = [], start
    INFO_MSGS = [
        "Request processed successfully", "Health check passed",
        "Cache hit ratio: {:.1f}%", "DB pool: {}/100 active",
        "Metrics flushed to collector", "Config refreshed",
    ]
    while t <= now:
        for svc in SERVICES:
            msg = random.choice(INFO_MSGS).format(random.uniform(85, 99), random.randint(5, 30))
            log_docs.append({"_index": "logs-quantumstate", "_source": {
                "@timestamp": t.isoformat(), "service": svc["name"],
                "region": svc["region"], "level": "INFO", "message": msg,
                "trace_id": f"trace-{random.randint(100000, 999999)}", "error_code": None,
            }})
        t += timedelta(minutes=5)

    for _ in helpers.parallel_bulk(es, log_docs, chunk_size=2000,
                                   raise_on_error=False, raise_on_exception=False):
        pass

    # Seed incidents
    inc_docs = []
    for inc in PAST_INCIDENTS:
        ts = now - timedelta(days=inc["days_ago"])
        # Compose incident_text if not explicitly provided (fallback)
        incident_text = inc.get(
            "incident_text",
            f"{inc['service']} {inc['anomaly_type']}: {inc['root_cause']} Resolution: {inc['action_taken']}",
        )
        inc_docs.append({"_index": "incidents-quantumstate", "_source": {
            "@timestamp": ts.isoformat(), "service": inc["service"],
            "region": inc["region"], "anomaly_type": inc["anomaly_type"],
            "root_cause": inc["root_cause"], "action_taken": inc["action_taken"],
            "incident_text": incident_text,
            "resolved_at": (ts + timedelta(seconds=inc["mttr_seconds"])).isoformat(),
            "mttr_seconds": inc["mttr_seconds"], "status": "resolved",
            "resolution_status": "RESOLVED",
            "pipeline_run": True,
            "guardian_verified": True,
        }})
    es.bulk(operations=[op for d in inc_docs for op in [{"index": {"_index": d["_index"]}}, d["_source"]]])

    for idx in QUANTUMSTATE_INDICES:
        try:
            es.indices.refresh(index=idx)
        except Exception:
            pass  # index may not exist if ELSER wasn't deployed

    # Seed runbooks if the index exists but is empty
    runbooks_seeded = 0
    try:
        if es.indices.exists(index="runbooks-quantumstate"):
            rb_count = es.count(index="runbooks-quantumstate").get("count", 0)
            if rb_count == 0:
                import sys as _sys
                _sys.path.insert(0, os.path.join(os.path.abspath(os.path.dirname(__file__)), "..", "..", "elastic-setup"))
                import seed_runbooks
                seed_runbooks.seed()
                runbooks_seeded = len(seed_runbooks.RUNBOOKS)
    except Exception as exc:
        print(f"[sim/setup] Warning: could not seed runbooks: {exc}")

    return {"ok": True, "metric_docs": len(docs), "log_docs": len(log_docs), "incidents_seeded": len(inc_docs), "runbooks_seeded": runbooks_seeded}


@router.post("/stream/start")
def start_stream():
    global _stream_thread, _stream_stop
    with _stream_lock:
        if _stream_thread and _stream_thread.is_alive():
            return {"ok": True, "streaming": True, "note": "already running"}
        es = get_es()
        stop_event = threading.Event()
        t = threading.Thread(target=_stream_loop, args=(es, stop_event), daemon=True)
        t.start()
        _stream_thread = t
        _stream_stop = stop_event
    return {"ok": True, "streaming": True}


@router.post("/stream/stop")
def stop_stream():
    global _stream_thread, _stream_stop
    with _stream_lock:
        if _stream_stop:
            _stream_stop.set()
        if _stream_thread:
            _stream_thread.join(timeout=5)
        _stream_thread = None
        _stream_stop = None
    return {"ok": True, "streaming": False}


@router.post("/inject/{scenario}")
def inject_scenario(scenario: str):
    es = get_es()
    mapping = {
        "memory_leak":          inject_memory_leak,
        "deployment_rollback":  inject_deployment_rollback,
        "error_spike":          inject_error_spike,
    }
    fn = mapping.get(scenario)
    if not fn:
        return {"ok": False, "error": f"Unknown scenario: {scenario}"}
    try:
        fn(es)
        return {"ok": True, "scenario": scenario}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@router.get("/mcp-runner/status")
def mcp_runner_status():
    """Return pending action count and the 5 most recent actions."""
    es = get_es()
    try:
        pending = es.count(
            index="remediation-actions-quantumstate",
            body={"query": {"term": {"status": "pending"}}},
        )["count"]
    except Exception:
        pending = 0
    try:
        result = es.search(
            index="remediation-actions-quantumstate",
            body={
                "size": 5,
                "sort": [{"@timestamp": "desc"}],
                "query": {"range": {"@timestamp": {"gte": "now-30m"}}},
                "_source": ["service", "action", "status", "exec_id", "executed_at", "@timestamp"],
            },
        )
        recent = [h["_source"] for h in result["hits"]["hits"]]
    except Exception:
        recent = []
    return {"pending": pending, "recent": recent}


@router.post("/mcp-runner/execute")
def mcp_runner_execute():
    """
    Synthetic MCP Runner — picks up one pending action and executes it.
    Mirrors what infra/mcp-runner/runner.py does with real Docker:
      1. Find oldest pending action
      2. Mark executing
      3. Write recovery metrics (the 'docker restart' equivalent)
      4. Mark executed + write result record
    """
    import uuid as _uuid
    es = get_es()

    # Find oldest pending action
    try:
        resp = es.search(
            index="remediation-actions-quantumstate",
            body={
                "size": 1,
                "query": {"term": {"status": "pending"}},
                "sort": [{"@timestamp": "asc"}],
            },
        )
    except Exception as exc:
        return {"ok": False, "error": str(exc), "executed": None}

    hits = resp["hits"]["hits"]
    if not hits:
        return {"ok": True, "executed": None, "message": "No pending actions"}

    hit      = hits[0]
    doc_id   = hit["_id"]
    doc      = hit["_source"]
    service  = doc.get("service", "")
    action   = doc.get("action", "restart_service")
    exec_id  = doc.get("exec_id") or str(_uuid.uuid4())[:8]
    inc_id   = doc.get("incident_id", "")
    now_iso  = datetime.now(timezone.utc).isoformat()

    # Mark as executing (optimistic lock equivalent)
    try:
        es.update(
            index="remediation-actions-quantumstate",
            id=doc_id,
            body={"doc": {"status": "executing", "runner_started_at": now_iso}},
        )
    except Exception:
        pass

    # Import recovery helpers from sibling router
    from routers.remediate import _write_recovery_metrics, _write_remediation_result

    points = _write_recovery_metrics(service, action)
    done_iso = datetime.now(timezone.utc).isoformat()

    # Mark executed
    try:
        es.update(
            index="remediation-actions-quantumstate",
            id=doc_id,
            body={"doc": {
                "status":       "executed",
                "executed_at":  done_iso,
                "runner_output": "synthetic_restart",
            }},
        )
    except Exception:
        pass

    _write_remediation_result(inc_id, service, action, exec_id, "success")

    return {
        "ok": True,
        "executed": {"service": service, "action": action, "exec_id": exec_id},
        "recovery_points_written": points,
        "message": f"Synthetic restart executed for {service} — {points} recovery metrics written",
    }


@router.post("/cleanup/incidents")
def clear_incidents():
    """Delete all incident, remediation, and guardian result docs — keeps metrics/logs intact."""
    es = get_es()
    results = {}
    for name in [
        "incidents-quantumstate",
        "remediation-actions-quantumstate",
        "remediation-results-quantumstate",
        "agent-decisions-quantumstate",
    ]:
        try:
            if es.indices.exists(index=name):
                es.delete_by_query(index=name, body={"query": {"match_all": {}}}, refresh=True)
                results[name] = "cleared"
            else:
                results[name] = "not found"
        except Exception as exc:
            results[name] = f"error: {exc}"
    return {"ok": True, "results": results}


@router.post("/cleanup/clear")
def clear_data():
    es = get_es()
    results = {}
    for name in QUANTUMSTATE_INDICES:
        try:
            if es.indices.exists(index=name):
                es.delete_by_query(index=name, body={"query": {"match_all": {}}}, refresh=True)
                results[name] = "cleared"
            else:
                results[name] = "not found"
        except Exception as exc:
            results[name] = f"error: {exc}"
    return {"ok": True, "results": results}


@router.post("/cleanup/delete-indices")
def delete_indices():
    es = get_es()
    results = {}
    for name in QUANTUMSTATE_INDICES:
        try:
            if es.indices.exists(index=name):
                es.indices.delete(index=name)
                results[name] = "deleted"
            else:
                results[name] = "not found"
        except Exception as exc:
            results[name] = f"error: {exc}"
    return {"ok": True, "results": results}
