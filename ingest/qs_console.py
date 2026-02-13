"""
QuantumState — Demo Console (Streamlit)

Single control panel for all data operations:
  • Setup    — create indices + load 24h baseline
  • Stream   — start/stop live metric streaming
  • Inject   — trigger anomaly scenarios
  • Cleanup  — delete non-QuantumState indices

Usage:
    streamlit run ingest/qs_console.py
"""

import os
import sys
import time
import random
import math
import threading
from datetime import datetime, timezone, timedelta

import streamlit as st
from elasticsearch import Elasticsearch
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(__file__))
from inject import inject_memory_leak, inject_deployment_rollback, inject_error_spike

load_dotenv()

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="QuantumState Console",
    page_icon="⚡",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

@st.cache_resource
def get_es() -> Elasticsearch:
    cloud_id = os.getenv("ELASTIC_CLOUD_ID")
    api_key  = os.getenv("ELASTIC_API_KEY")
    if not cloud_id or not api_key:
        st.error("ELASTIC_CLOUD_ID and ELASTIC_API_KEY not found in .env")
        st.stop()
    return Elasticsearch(cloud_id=cloud_id, api_key=api_key, request_timeout=15)

# ---------------------------------------------------------------------------
# Setup helpers (inlined from setup.py)
# ---------------------------------------------------------------------------

QUANTUMSTATE_INDICES = {
    "metrics-quantumstate": {
        "mappings": {
            "properties": {
                "@timestamp":   {"type": "date"},
                "service":      {"type": "keyword"},
                "region":       {"type": "keyword"},
                "metric_type":  {"type": "keyword"},
                "value":        {"type": "double"},
                "unit":         {"type": "keyword"},
            }
        }
    },
    "logs-quantumstate": {
        "mappings": {
            "properties": {
                "@timestamp":   {"type": "date"},
                "service":      {"type": "keyword"},
                "region":       {"type": "keyword"},
                "level":        {"type": "keyword"},
                "message":      {"type": "text"},
                "trace_id":     {"type": "keyword"},
                "error_code":   {"type": "keyword"},
            }
        }
    },
    "incidents-quantumstate": {
        "mappings": {
            "properties": {
                "@timestamp":       {"type": "date"},
                "service":          {"type": "keyword"},
                "region":           {"type": "keyword"},
                "anomaly_type":     {"type": "keyword"},
                "root_cause":       {"type": "text"},
                "actions_taken":    {"type": "text"},
                "resolved_at":      {"type": "date"},
                "mttr_seconds":     {"type": "integer"},
                "status":           {"type": "keyword"},
            }
        }
    },
    "agent-decisions-quantumstate": {
        "mappings": {
            "properties": {
                "@timestamp":   {"type": "date"},
                "agent":        {"type": "keyword"},
                "decision":     {"type": "text"},
                "confidence":   {"type": "integer"},
                "service":      {"type": "keyword"},
                "context":      {"type": "object", "enabled": False},
            }
        }
    },
}

SERVICES = [
    {"name": "payment-service",   "region": "us-east-1"},
    {"name": "checkout-service",  "region": "us-east-1"},
    {"name": "auth-service",      "region": "us-west-2"},
    {"name": "inventory-service", "region": "eu-west-1"},
]

BASELINES = {
    "memory_percent":     {"mean": 52, "std": 4},
    "cpu_percent":        {"mean": 35, "std": 8},
    "error_rate":         {"mean": 0.4, "std": 0.2},
    "request_latency_ms": {"mean": 120, "std": 25},
    "requests_per_min":   {"mean": 850, "std": 120},
}

METRIC_UNITS = {
    "memory_percent":     "percent",
    "cpu_percent":        "percent",
    "error_rate":         "errors_per_min",
    "request_latency_ms": "ms",
    "requests_per_min":   "requests_per_min",
}

PAST_INCIDENTS = [
    {
        "service": "payment-service", "region": "us-east-1",
        "anomaly_type": "memory_leak_progressive",
        "root_cause": "Memory leak in JDBC connection pool introduced by deploy v2.1.0. Connections not released after timeout.",
        "actions_taken": "Rolled back to v2.0.9. Restarted service. Memory stabilised at 52%.",
        "mttr_seconds": 2820, "days_ago": 14,
    },
    {
        "service": "auth-service", "region": "us-west-2",
        "anomaly_type": "error_spike_sudden",
        "root_cause": "Redis session cache became unavailable. Auth service fell back to DB lookups, overwhelming connections.",
        "actions_taken": "Restarted Redis cluster. Scaled DB connection pool. Added circuit breaker.",
        "mttr_seconds": 960, "days_ago": 7,
    },
    {
        "service": "checkout-service", "region": "us-east-1",
        "anomaly_type": "deployment_regression",
        "root_cause": "Deploy v3.4.2 introduced unhandled NPE in cart serialisation, causing 5xx on all checkout requests.",
        "actions_taken": "Immediate rollback to v3.4.1. Error rate returned to baseline within 2 minutes.",
        "mttr_seconds": 480, "days_ago": 3,
    },
    {
        "service": "inventory-service", "region": "eu-west-1",
        "anomaly_type": "memory_leak_progressive",
        "root_cause": "Unbounded in-memory cache for product catalogue growing without eviction policy.",
        "actions_taken": "Added LRU eviction with 10k item limit. Deployed hotfix v1.8.3.",
        "mttr_seconds": 5400, "days_ago": 21,
    },
]


def run_setup(es: Elasticsearch, progress, status):
    from elasticsearch import helpers

    def clamp(v, lo, hi): return max(lo, min(hi, v))

    # Step 1: Create indices
    status.text("Creating indices...")
    progress.progress(5)
    for name, body in QUANTUMSTATE_INDICES.items():
        if es.indices.exists(index=name):
            pass
        else:
            es.indices.create(index=name, body=body)
    progress.progress(15)

    # Step 2: Baseline metrics (24h, 1 doc/min/service/metric)
    status.text("Generating 24h baseline metrics...")
    now   = datetime.now(timezone.utc)
    start = now - timedelta(hours=24)
    docs  = []
    t = start
    while t <= now:
        for svc in SERVICES:
            hour_offset = t.hour + t.minute / 60
            diurnal = math.sin(math.pi * hour_offset / 12)
            for metric, cfg in BASELINES.items():
                value = random.gauss(cfg["mean"] + diurnal * cfg["std"] * 0.5, cfg["std"])
                if metric in ("memory_percent", "cpu_percent"):
                    value = clamp(value, 5, 95)
                elif metric == "error_rate":
                    value = clamp(value, 0, 5)
                elif metric == "request_latency_ms":
                    value = clamp(value, 10, 2000)
                else:
                    value = clamp(value, 0, 5000)
                docs.append({
                    "_index": "metrics-quantumstate",
                    "_source": {
                        "@timestamp": t.isoformat(), "service": svc["name"],
                        "region": svc["region"], "metric_type": metric,
                        "value": round(value, 2), "unit": METRIC_UNITS[metric],
                    }
                })
        t += timedelta(minutes=1)
    progress.progress(40)

    status.text(f"Indexing {len(docs):,} metric docs...")
    for ok, _ in helpers.parallel_bulk(es, docs, chunk_size=2000, thread_count=4,
                                        raise_on_error=False, raise_on_exception=False):
        pass
    progress.progress(65)

    # Step 3: Baseline logs
    status.text("Generating baseline logs...")
    log_docs = []
    INFO_MSGS = [
        "Request processed successfully", "Health check passed",
        "Cache hit ratio: {:.1f}%", "DB pool: {}/100 active",
        "Metrics flushed to collector", "Config refreshed",
    ]
    t = start
    while t <= now:
        for svc in SERVICES:
            msg = random.choice(INFO_MSGS).format(
                random.uniform(85, 99), random.randint(5, 30)
            )
            log_docs.append({
                "_index": "logs-quantumstate",
                "_source": {
                    "@timestamp": t.isoformat(), "service": svc["name"],
                    "region": svc["region"], "level": "INFO",
                    "message": msg, "trace_id": f"trace-{random.randint(100000,999999)}",
                    "error_code": None,
                }
            })
        t += timedelta(minutes=5)
    for ok, _ in helpers.parallel_bulk(es, log_docs, chunk_size=2000, raise_on_error=False,
                                        raise_on_exception=False):
        pass
    progress.progress(85)

    # Step 4: Past incidents
    status.text("Seeding past incidents...")
    inc_docs = []
    for inc in PAST_INCIDENTS:
        ts = now - timedelta(days=inc["days_ago"])
        inc_docs.append({
            "_index": "incidents-quantumstate",
            "_source": {
                "@timestamp": ts.isoformat(), "service": inc["service"],
                "region": inc["region"], "anomaly_type": inc["anomaly_type"],
                "root_cause": inc["root_cause"], "actions_taken": inc["actions_taken"],
                "resolved_at": (ts + timedelta(seconds=inc["mttr_seconds"])).isoformat(),
                "mttr_seconds": inc["mttr_seconds"], "status": "resolved",
            }
        })
    es.bulk(operations=[
        op for d in inc_docs
        for op in [{"index": {"_index": d["_index"]}}, d["_source"]]
    ])

    for idx in QUANTUMSTATE_INDICES:
        es.indices.refresh(index=idx)

    progress.progress(100)
    status.text("Setup complete.")

# ---------------------------------------------------------------------------
# Streamer (background thread)
# ---------------------------------------------------------------------------

def stream_loop(es: Elasticsearch, stop_event: threading.Event):
    while not stop_event.is_set():
        now = datetime.now(timezone.utc)
        hour_offset = now.hour + now.minute / 60
        diurnal = math.sin(math.pi * hour_offset / 12)

        docs = []
        for svc in SERVICES:
            for metric, cfg in BASELINES.items():
                value = random.gauss(cfg["mean"] + diurnal * cfg["std"] * 0.5, cfg["std"])
                if metric in ("memory_percent", "cpu_percent"):
                    value = max(5, min(95, value))
                elif metric == "error_rate":
                    value = max(0, min(5, value))
                docs.append({
                    "@timestamp": now.isoformat(), "service": svc["name"],
                    "region": svc["region"], "metric_type": metric,
                    "value": round(value, 2), "unit": METRIC_UNITS[metric],
                })

        try:
            es.bulk(operations=[
                op for d in docs
                for op in [{"index": {"_index": "metrics-quantumstate"}}, d]
            ])
        except Exception:
            pass

        stop_event.wait(30)

# ---------------------------------------------------------------------------
# Health helpers
# ---------------------------------------------------------------------------

def get_latest_metric(es, service, metric_type):
    try:
        resp = es.search(index="metrics-quantumstate", body={
            "size": 1,
            "query": {"bool": {"filter": [
                {"term": {"service": service}},
                {"term": {"metric_type": metric_type}},
            ]}},
            "sort": [{"@timestamp": "desc"}],
        })
        hits = resp["hits"]["hits"]
        return hits[0]["_source"]["value"] if hits else None
    except Exception:
        return None

def sev(value, warn, crit):
    if value is None: return "⚪"
    if value >= crit: return "🔴"
    if value >= warn: return "🟡"
    return "🟢"

# ---------------------------------------------------------------------------
# Main UI
# ---------------------------------------------------------------------------

st.title("⚡ QuantumState Console")

es = get_es()

# Session state init
if "stream_thread" not in st.session_state:
    st.session_state.stream_thread = None
if "stream_stop" not in st.session_state:
    st.session_state.stream_stop = None

tab_setup, tab_stream, tab_inject, tab_health, tab_cleanup = st.tabs([
    "🔧 Setup", "📡 Stream", "💉 Inject", "📊 Health", "🗑️ Cleanup"
])

# ── Setup ──────────────────────────────────────────────────────────────────
with tab_setup:
    st.markdown("### One-time setup")
    st.markdown(
        "Creates the four QuantumState indices and loads 24 hours of healthy "
        "baseline data. Safe to re-run — existing indices are skipped."
    )
    existing = [n for n in QUANTUMSTATE_INDICES if es.indices.exists(index=n)]
    if existing:
        st.info(f"Already exists: {', '.join(existing)}")

    if st.button("Run Setup", type="primary", use_container_width=True):
        progress = st.progress(0)
        status   = st.empty()
        try:
            run_setup(es, progress, status)
            st.success("✅ Setup complete. Switch to **Stream** to start streaming.")
        except Exception as e:
            st.error(f"Setup failed: {e}")

# ── Stream ─────────────────────────────────────────────────────────────────
with tab_stream:
    st.markdown("### Live metric streamer")
    st.markdown("Emits fresh metrics every 30 seconds so dashboards stay live.")

    is_running = (
        st.session_state.stream_thread is not None
        and st.session_state.stream_thread.is_alive()
    )

    if is_running:
        st.success("🟢 Streamer is running")
        if st.button("Stop Streamer", use_container_width=True):
            st.session_state.stream_stop.set()
            st.session_state.stream_thread.join(timeout=5)
            st.session_state.stream_thread = None
            st.session_state.stream_stop   = None
            st.rerun()
    else:
        st.warning("⚫ Streamer is stopped")
        if st.button("Start Streamer", type="primary", use_container_width=True):
            stop_event = threading.Event()
            thread = threading.Thread(
                target=stream_loop,
                args=(es, stop_event),
                daemon=True,
            )
            thread.start()
            st.session_state.stream_thread = thread
            st.session_state.stream_stop   = stop_event
            st.rerun()

# ── Inject ─────────────────────────────────────────────────────────────────
with tab_inject:
    st.markdown("### Inject anomaly scenario")
    st.markdown(
        "Bulk-loads backdated anomaly data — agents detect it immediately "
        "on the next run. Pick your scenario and fire."
    )

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("#### 🧠 Memory Leak")
        st.caption("payment-service · us-east-1")
        st.markdown("Memory 55% → 89% over 25 min. JVM heap / connection pool leak.")
        if st.button("Inject", key="ml", type="primary", use_container_width=True):
            with st.spinner("Injecting..."):
                try:
                    inject_memory_leak(es)
                    st.success("✅ Memory leak injected")
                except Exception as e:
                    st.error(str(e))

    with col2:
        st.markdown("#### 💥 Deployment Rollback")
        st.caption("checkout-service · us-east-1")
        st.markdown("Deploy v3.5.0 → error rate 0.4 → 18/min. NPE in cart serialiser.")
        if st.button("Inject", key="dr", type="primary", use_container_width=True):
            with st.spinner("Injecting..."):
                try:
                    inject_deployment_rollback(es)
                    st.success("✅ Deployment rollback injected")
                except Exception as e:
                    st.error(str(e))

    with col3:
        st.markdown("#### ⚡ Error Spike")
        st.caption("auth-service · us-west-2")
        st.markdown("Errors 0.3 → 28/min instantly. Redis cache went offline.")
        if st.button("Inject", key="es", type="primary", use_container_width=True):
            with st.spinner("Injecting..."):
                try:
                    inject_error_spike(es)
                    st.success("✅ Error spike injected")
                except Exception as e:
                    st.error(str(e))

# ── Health ─────────────────────────────────────────────────────────────────
with tab_health:
    st.markdown("### Live service health")
    st.caption("Showing latest metric value per service. Refresh page to update.")

    cols = st.columns(4)
    for col, svc in zip(cols, SERVICES):
        with col:
            mem = get_latest_metric(es, svc["name"], "memory_percent")
            cpu = get_latest_metric(es, svc["name"], "cpu_percent")
            err = get_latest_metric(es, svc["name"], "error_rate")
            lat = get_latest_metric(es, svc["name"], "request_latency_ms")

            if any([mem and mem >= 80, err and err >= 10, cpu and cpu >= 85]):
                badge = "🔴 CRITICAL"
            elif any([mem and mem >= 65, err and err >= 3, cpu and cpu >= 65]):
                badge = "🟡 WARNING"
            else:
                badge = "🟢 HEALTHY"

            st.markdown(f"**{svc['name']}**")
            st.caption(svc["region"])
            st.markdown(badge)
            st.markdown(f"{sev(mem, 65, 80)} Memory: `{mem:.1f}%`"       if mem else "Memory: –")
            st.markdown(f"{sev(cpu, 65, 85)} CPU: `{cpu:.1f}%`"           if cpu else "CPU: –")
            st.markdown(f"{sev(err,  3, 10)} Errors: `{err:.1f}/min`"     if err else "Errors: –")
            st.markdown(f"{sev(lat, 500,1000)} Latency: `{lat:.0f}ms`"    if lat else "Latency: –")

    st.divider()
    st.markdown("### Recent logs")
    selected = st.selectbox("Service", [s["name"] for s in SERVICES])
    try:
        since = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
        resp  = es.search(index="logs-quantumstate", body={
            "size": 12,
            "query": {"bool": {"filter": [
                {"term": {"service": selected}},
                {"range": {"@timestamp": {"gte": since}}},
            ]}},
            "sort": [{"@timestamp": "desc"}],
        })
        logs = [h["_source"] for h in resp["hits"]["hits"]]
        ICONS = {"INFO": "🔵", "WARN": "🟡", "WARNING": "🟡", "ERROR": "🔴", "CRITICAL": "🔴"}
        if logs:
            for log in logs:
                ts    = log.get("@timestamp", "")[:19].replace("T", " ")
                level = log.get("level", "INFO")
                st.markdown(f"`{ts}` {ICONS.get(level,'⚪')} **{level}** — {log.get('message','')}")
        else:
            st.info("No logs in the last 30 minutes.")
    except Exception as e:
        st.error(str(e))

# ── Cleanup ────────────────────────────────────────────────────────────────
with tab_cleanup:
    st.markdown("### Index cleanup")
    st.markdown("Lists all non-system indices. Delete anything that isn't QuantumState.")

    try:
        all_indices = sorted([
            name for name in es.indices.get(index="*").keys()
            if not name.startswith(".")
        ])
    except Exception as e:
        st.error(str(e))
        all_indices = []

    qs_names = set(QUANTUMSTATE_INDICES.keys())
    other    = [i for i in all_indices if i not in qs_names]
    qs_found = [i for i in all_indices if i in qs_names]

    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown("**QuantumState indices** ✅")
        for name in qs_found:
            try:
                count = es.count(index=name)["count"]
                st.markdown(f"- `{name}` — {count:,} docs")
            except Exception:
                st.markdown(f"- `{name}`")

    with col_b:
        st.markdown("**Other indices**")
        if not other:
            st.info("None — all clean.")
        else:
            for name in other:
                try:
                    count = es.count(index=name)["count"]
                    st.markdown(f"- `{name}` — {count:,} docs")
                except Exception:
                    st.markdown(f"- `{name}`")

    if other:
        st.divider()
        st.warning(f"{len(other)} non-QuantumState indices found.")
        if st.button(f"Delete all {len(other)} other indices", type="primary", use_container_width=True):
            deleted, failed = [], []
            for name in other:
                try:
                    es.indices.delete(index=name)
                    deleted.append(name)
                except Exception as e:
                    failed.append(f"{name} ({e})")
            if deleted:
                st.success(f"Deleted: {', '.join(deleted)}")
            if failed:
                st.error(f"Failed: {', '.join(failed)}")
            st.rerun()
