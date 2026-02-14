"""
QuantumState — QS Console

Usage:
    streamlit run ingest/qs_console.py
"""

import os
import sys
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

# ── Page config ──────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="QuantumState",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Global CSS ───────────────────────────────────────────────────────────────

st.markdown("""
<style>
  /* Import font */
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

  html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
  }

  /* Hide default Streamlit chrome */
  #MainMenu, footer, header { visibility: hidden; }
  .block-container { padding: 2rem 2.5rem 1rem; }

  /* ── Header bar ── */
  .qs-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 0 1.5rem 0;
    border-bottom: 1px solid #1A1A1A;
    margin-bottom: 1.5rem;
  }
  .qs-logo {
    font-size: 1.4rem;
    font-weight: 700;
    letter-spacing: -0.5px;
    color: #F8FAFC;
  }
  .qs-logo span { color: #FF6B00; }
  .qs-tagline {
    font-size: 0.75rem;
    color: #64748B;
    font-weight: 400;
    margin-top: 2px;
  }
  .qs-conn-badge {
    font-size: 0.72rem;
    font-family: 'JetBrains Mono', monospace;
    padding: 4px 12px;
    border-radius: 20px;
    font-weight: 500;
  }
  .qs-conn-ok   { background: #052e16; color: #4ADE80; border: 1px solid #166534; }
  .qs-conn-fail { background: #2d0f0f; color: #f87171; border: 1px solid #7f1d1d; }

  /* ── Tabs ── */
  .stTabs [data-baseweb="tab-list"] {
    gap: 0;
    background: #111111;
    border-radius: 10px;
    padding: 4px;
    border: 1px solid #1A1A1A;
  }
  .stTabs [data-baseweb="tab"] {
    border-radius: 7px;
    padding: 8px 20px;
    font-size: 0.82rem;
    font-weight: 500;
    color: #64748B;
    background: transparent;
    border: none;
  }
  .stTabs [aria-selected="true"] {
    background: #1A1A1A !important;
    color: #F1F5F9 !important;
  }

  /* ── Metric cards ── */
  .metric-card {
    background: #111111;
    border: 1px solid #1A1A1A;
    border-radius: 12px;
    padding: 1.2rem 1.4rem;
    height: 100%;
  }
  .metric-card-title {
    font-size: 0.72rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #64748B;
    margin-bottom: 0.6rem;
  }
  .metric-card-service {
    font-size: 0.95rem;
    font-weight: 600;
    color: #F1F5F9;
    margin-bottom: 0.2rem;
  }
  .metric-card-region {
    font-size: 0.72rem;
    color: #475569;
    font-family: 'JetBrains Mono', monospace;
    margin-bottom: 0.9rem;
  }
  .metric-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 5px 0;
    border-bottom: 1px solid #1A1A1A;
    font-size: 0.8rem;
  }
  .metric-row:last-child { border-bottom: none; }
  .metric-label { color: #94A3B8; }
  .metric-value {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.82rem;
    font-weight: 500;
    color: #E2E8F0;
  }
  .metric-value.warn  { color: #FBBF24; }
  .metric-value.crit  { color: #F87171; }
  .metric-value.ok    { color: #4ADE80; }

  /* Status pill */
  .status-pill {
    display: inline-block;
    font-size: 0.7rem;
    font-weight: 600;
    padding: 3px 10px;
    border-radius: 20px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 0.8rem;
  }
  .pill-ok   { background: #052e16; color: #4ADE80; border: 1px solid #166534; }
  .pill-warn { background: #1c1400; color: #fbbf24; border: 1px solid #854d0e; }
  .pill-crit { background: #2d0f0f; color: #f87171; border: 1px solid #7f1d1d; }

  /* ── Inject scenario cards ── */
  .scenario-card {
    background: #111111;
    border: 1px solid #1A1A1A;
    border-radius: 12px;
    padding: 1.4rem;
    min-height: 220px;
  }
  .scenario-title {
    font-size: 1rem;
    font-weight: 600;
    color: #F1F5F9;
    margin-bottom: 0.3rem;
  }
  .scenario-service {
    font-size: 0.72rem;
    font-family: 'JetBrains Mono', monospace;
    color: #FF6B00;
    margin-bottom: 0.8rem;
  }
  .scenario-desc {
    font-size: 0.8rem;
    color: #94A3B8;
    line-height: 1.6;
    margin-bottom: 1rem;
  }
  .scenario-tag {
    display: inline-block;
    font-size: 0.68rem;
    font-weight: 500;
    padding: 2px 8px;
    border-radius: 4px;
    margin-right: 4px;
    background: #1A1A1A;
    color: #94A3B8;
    font-family: 'JetBrains Mono', monospace;
  }

  /* ── Log viewer ── */
  .log-line {
    display: flex;
    gap: 10px;
    align-items: flex-start;
    padding: 6px 10px;
    border-radius: 6px;
    margin-bottom: 3px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.76rem;
  }
  .log-line:hover { background: #1A1A1A; }
  .log-ts    { color: #475569; flex-shrink: 0; }
  .log-level { font-weight: 600; flex-shrink: 0; min-width: 60px; }
  .log-msg   { color: #CBD5E1; flex: 1; }
  .level-INFO     { color: #60A5FA; }
  .level-WARN, .level-WARNING { color: #FBBF24; }
  .level-ERROR    { color: #F87171; }
  .level-CRITICAL { color: #C084FC; }

  /* ── Section header ── */
  .section-header {
    font-size: 0.72rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: #475569;
    margin-bottom: 1rem;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid #1A1A1A;
  }

  /* ── Index table ── */
  .idx-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 8px 12px;
    border-radius: 8px;
    margin-bottom: 4px;
    background: #111111;
    border: 1px solid #1A1A1A;
    font-size: 0.8rem;
  }
  .idx-name {
    font-family: 'JetBrains Mono', monospace;
    color: #E2E8F0;
  }
  .idx-count { color: #64748B; font-size: 0.75rem; }
  .idx-qs    { border-left: 3px solid #FF6B00; }
  .idx-other { border-left: 3px solid #374151; }

  /* ── Streamlit button overrides ── */
  .stButton > button {
    border-radius: 8px;
    font-weight: 500;
    font-size: 0.82rem;
    transition: all 0.15s ease;
    border: 1px solid transparent;
  }
  .stButton > button[kind="primary"] {
    background: #FF6B00;
    color: #0A0A0A;
    border-color: #FF6B00;
  }
  .stButton > button[kind="primary"]:hover {
    background: #FF8C33;
    border-color: #FF8C33;
  }

  /* Progress bar */
  .stProgress > div > div { background: #FF6B00; }

  /* ── Pipeline step cards ── */
  .pipeline-step {
    background: #111111;
    border: 1px solid #1A1A1A;
    border-radius: 12px;
    padding: 1.2rem 1.4rem;
    margin-bottom: 0.8rem;
    position: relative;
  }
  .pipeline-step.active  { border-color: #FF6B00; }
  .pipeline-step.done    { border-color: #166534; }
  .pipeline-step.waiting { opacity: 0.45; }
  .pipeline-step-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 0.5rem;
  }
  .pipeline-step-name {
    font-size: 0.88rem;
    font-weight: 600;
    color: #F1F5F9;
  }
  .pipeline-step-role {
    font-size: 0.72rem;
    color: #64748B;
    text-transform: uppercase;
    letter-spacing: 0.07em;
  }
  .pipeline-output {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.76rem;
    color: #94A3B8;
    white-space: pre-wrap;
    line-height: 1.6;
    background: #0D0D0D;
    border-radius: 8px;
    padding: 0.8rem 1rem;
    margin-top: 0.6rem;
    max-height: 280px;
    overflow-y: auto;
    border: 1px solid #1A1A1A;
  }
  .pipeline-connector {
    width: 2px;
    height: 20px;
    background: #1A1A1A;
    margin: 0 auto 0.8rem;
  }


  /* Alerts */
  .stSuccess { background: #052e16; border: 1px solid #166534; border-radius: 8px; }
  .stError   { background: #2d0f0f; border: 1px solid #7f1d1d; border-radius: 8px; }
  .stInfo    { background: #0c1a2e; border: 1px solid #1e3a5f; border-radius: 8px; }
  .stWarning { background: #1c1400; border: 1px solid #854d0e; border-radius: 8px; }
</style>
""", unsafe_allow_html=True)

# ── Data constants ────────────────────────────────────────────────────────────

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
            "@timestamp": {"type": "date"}, "service": {"type": "keyword"},
            "region": {"type": "keyword"}, "anomaly_type": {"type": "keyword"},
            "root_cause": {"type": "text"}, "actions_taken": {"type": "text"},
            "resolved_at": {"type": "date"}, "mttr_seconds": {"type": "integer"},
            "status": {"type": "keyword"},
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

# ── Connection ────────────────────────────────────────────────────────────────

@st.cache_resource
def get_es():
    cloud_id = os.getenv("ELASTIC_CLOUD_ID")
    api_key  = os.getenv("ELASTIC_API_KEY")
    if not cloud_id or not api_key:
        return None
    try:
        es = Elasticsearch(cloud_id=cloud_id, api_key=api_key, request_timeout=15)
        es.info()
        return es
    except Exception:
        return None

# ── Helpers ───────────────────────────────────────────────────────────────────

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

def metric_class(value, warn, crit):
    if value is None:  return ""
    if value >= crit:  return "crit"
    if value >= warn:  return "warn"
    return "ok"

def fmt(value, decimals=1, suffix=""):
    if value is None: return "—"
    return f"{value:.{decimals}f}{suffix}"

def run_setup(es, progress, status):
    from elasticsearch import helpers

    def clamp(v, lo, hi): return max(lo, min(hi, v))

    status.markdown('<p style="color:#94A3B8;font-size:0.85rem">Creating indices…</p>', unsafe_allow_html=True)
    progress.progress(5)
    for name, body in QUANTUMSTATE_INDICES.items():
        if not es.indices.exists(index=name):
            es.indices.create(index=name, body=body)
    progress.progress(15)

    status.markdown('<p style="color:#94A3B8;font-size:0.85rem">Generating 24 h baseline metrics…</p>', unsafe_allow_html=True)
    now, start = datetime.now(timezone.utc), datetime.now(timezone.utc) - timedelta(hours=24)
    docs, t = [], start
    while t <= now:
        for svc in SERVICES:
            diurnal = math.sin(math.pi * (t.hour + t.minute / 60) / 12)
            for metric, cfg in BASELINES.items():
                v = random.gauss(cfg["mean"] + diurnal * cfg["std"] * 0.5, cfg["std"])
                v = clamp(v, 5, 95) if metric in ("memory_percent","cpu_percent") else clamp(v, 0, 5) if metric == "error_rate" else clamp(v, 10, 2000) if metric == "request_latency_ms" else clamp(v, 0, 5000)
                docs.append({"_index": "metrics-quantumstate", "_source": {
                    "@timestamp": t.isoformat(), "service": svc["name"],
                    "region": svc["region"], "metric_type": metric,
                    "value": round(v, 2), "unit": METRIC_UNITS[metric],
                }})
        t += timedelta(minutes=1)
    progress.progress(40)

    status.markdown(f'<p style="color:#94A3B8;font-size:0.85rem">Indexing {len(docs):,} metric documents…</p>', unsafe_allow_html=True)
    for ok, _ in helpers.parallel_bulk(es, docs, chunk_size=2000, thread_count=4,
                                        raise_on_error=False, raise_on_exception=False):
        pass
    progress.progress(65)

    status.markdown('<p style="color:#94A3B8;font-size:0.85rem">Generating baseline logs…</p>', unsafe_allow_html=True)
    log_docs, t = [], start
    INFO_MSGS = ["Request processed successfully", "Health check passed",
                 "Cache hit ratio: {:.1f}%", "DB pool: {}/100 active",
                 "Metrics flushed to collector", "Config refreshed"]
    while t <= now:
        for svc in SERVICES:
            msg = random.choice(INFO_MSGS).format(random.uniform(85,99), random.randint(5,30))
            log_docs.append({"_index": "logs-quantumstate", "_source": {
                "@timestamp": t.isoformat(), "service": svc["name"],
                "region": svc["region"], "level": "INFO", "message": msg,
                "trace_id": f"trace-{random.randint(100000,999999)}", "error_code": None,
            }})
        t += timedelta(minutes=5)
    for ok, _ in helpers.parallel_bulk(es, log_docs, chunk_size=2000, raise_on_error=False,
                                        raise_on_exception=False):
        pass
    progress.progress(85)

    status.markdown('<p style="color:#94A3B8;font-size:0.85rem">Seeding historical incidents…</p>', unsafe_allow_html=True)
    inc_docs = []
    for inc in PAST_INCIDENTS:
        ts = now - timedelta(days=inc["days_ago"])
        inc_docs.append({"_index": "incidents-quantumstate", "_source": {
            "@timestamp": ts.isoformat(), "service": inc["service"],
            "region": inc["region"], "anomaly_type": inc["anomaly_type"],
            "root_cause": inc["root_cause"], "actions_taken": inc["actions_taken"],
            "resolved_at": (ts + timedelta(seconds=inc["mttr_seconds"])).isoformat(),
            "mttr_seconds": inc["mttr_seconds"], "status": "resolved",
        }})
    es.bulk(operations=[op for d in inc_docs for op in [{"index": {"_index": d["_index"]}}, d["_source"]]])
    for idx in QUANTUMSTATE_INDICES:
        es.indices.refresh(index=idx)
    progress.progress(100)

def stream_loop(es, stop_event):
    while not stop_event.is_set():
        now = datetime.now(timezone.utc)
        diurnal = math.sin(math.pi * (now.hour + now.minute / 60) / 12)
        docs = []
        for svc in SERVICES:
            for metric, cfg in BASELINES.items():
                v = random.gauss(cfg["mean"] + diurnal * cfg["std"] * 0.5, cfg["std"])
                v = max(5, min(95, v)) if metric in ("memory_percent","cpu_percent") else max(0, min(5, v))
                docs.append({"@timestamp": now.isoformat(), "service": svc["name"],
                              "region": svc["region"], "metric_type": metric,
                              "value": round(v, 2), "unit": METRIC_UNITS[metric]})
        try:
            es.bulk(operations=[op for d in docs for op in [{"index": {"_index": "metrics-quantumstate"}}, d]])
        except Exception:
            pass
        stop_event.wait(30)

# ── Session state ─────────────────────────────────────────────────────────────

if "stream_thread" not in st.session_state:
    st.session_state.stream_thread = None
if "stream_stop" not in st.session_state:
    st.session_state.stream_stop = None

# ── Header ────────────────────────────────────────────────────────────────────

es = get_es()
conn_html = (
    '<span class="qs-conn-badge qs-conn-ok">● CONNECTED</span>'
    if es else
    '<span class="qs-conn-badge qs-conn-fail">● DISCONNECTED</span>'
)

st.markdown(f"""
<div class="qs-header">
  <div>
    <div class="qs-logo">Quantum<span>State</span></div>
    <div class="qs-tagline">Autonomous SRE — Elastic Agent Builder Demo Console</div>
  </div>
  {conn_html}
</div>
""", unsafe_allow_html=True)

if not es:
    st.error("Cannot connect to Elasticsearch. Check ELASTIC_CLOUD_ID and ELASTIC_API_KEY in .env")
    st.stop()

# ── Tabs ──────────────────────────────────────────────────────────────────────

tab_setup, tab_stream, tab_inject, tab_pipeline, tab_health, tab_cleanup = st.tabs([
    "Setup", "Stream", "Inject", "Pipeline", "Health", "Cleanup"
])

# ─────────────────────────────────────────────────────────────────────────────
# SETUP
# ─────────────────────────────────────────────────────────────────────────────
with tab_setup:
    st.markdown('<div class="section-header">One-time index setup</div>', unsafe_allow_html=True)

    existing = [n for n in QUANTUMSTATE_INDICES if es.indices.exists(index=n)]
    missing  = [n for n in QUANTUMSTATE_INDICES if n not in existing]

    col_info, col_btn = st.columns([3, 1])
    with col_info:
        st.markdown("""
        <p style="color:#94A3B8;font-size:0.88rem;line-height:1.7">
        Creates the four QuantumState Elasticsearch indices and loads
        <strong style="color:#E2E8F0">24 hours of healthy baseline data</strong>
        (~28,000 metric documents + logs + 4 historical incidents).
        Safe to re-run — existing indices are skipped.
        </p>
        """, unsafe_allow_html=True)

    with col_btn:
        run = st.button("Run Setup", type="primary", use_container_width=True)

    # Index status grid
    st.markdown('<div style="height:1rem"></div>', unsafe_allow_html=True)
    cols = st.columns(4)
    for col, (name, _) in zip(cols, QUANTUMSTATE_INDICES.items()):
        with col:
            exists = name in existing
            try:
                count = es.count(index=name)["count"] if exists else 0
            except Exception:
                count = 0
            pill = '<span class="status-pill pill-ok">EXISTS</span>' if exists else '<span class="status-pill pill-warn">MISSING</span>'
            short = name.replace("-quantumstate", "")
            st.markdown(f"""
            <div class="metric-card">
              <div class="metric-card-title">{short}</div>
              {pill}
              <div style="font-family:'JetBrains Mono',monospace;font-size:0.82rem;color:#94A3B8">
                {f"{count:,} docs" if exists else "not created"}
              </div>
            </div>
            """, unsafe_allow_html=True)

    if run:
        st.markdown('<div style="height:1rem"></div>', unsafe_allow_html=True)
        progress = st.progress(0)
        status   = st.empty()
        try:
            run_setup(es, progress, status)
            st.success("Setup complete — switch to **Stream** to start live data.")
        except Exception as e:
            st.error(f"Setup failed: {e}")

# ─────────────────────────────────────────────────────────────────────────────
# STREAM
# ─────────────────────────────────────────────────────────────────────────────
with tab_stream:
    st.markdown('<div class="section-header">Live metric streamer</div>', unsafe_allow_html=True)

    is_running = (
        st.session_state.stream_thread is not None
        and st.session_state.stream_thread.is_alive()
    )

    col_status, col_ctl = st.columns([3, 1])

    with col_status:
        if is_running:
            st.markdown("""
            <div class="metric-card" style="border-color:#166534">
              <span class="status-pill pill-ok">STREAMING</span>
              <p style="color:#94A3B8;font-size:0.85rem;margin:0.5rem 0 0">
              Emitting fresh metrics every <strong style="color:#E2E8F0">30 seconds</strong>
              across all 4 services — 20 documents per tick.
              Kibana dashboards will stay live while this is running.
              </p>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div class="metric-card">
              <span class="status-pill pill-warn">STOPPED</span>
              <p style="color:#94A3B8;font-size:0.85rem;margin:0.5rem 0 0">
              Streamer is not running. Start it to keep the "now" data window
              alive in Kibana. Required for live dashboard charts during a demo.
              </p>
            </div>
            """, unsafe_allow_html=True)

    with col_ctl:
        if is_running:
            if st.button("Stop", use_container_width=True):
                st.session_state.stream_stop.set()
                st.session_state.stream_thread.join(timeout=5)
                st.session_state.stream_thread = None
                st.session_state.stream_stop   = None
                st.rerun()
        else:
            if st.button("Start Streamer", type="primary", use_container_width=True):
                stop_event = threading.Event()
                thread = threading.Thread(target=stream_loop, args=(es, stop_event), daemon=True)
                thread.start()
                st.session_state.stream_thread = thread
                st.session_state.stream_stop   = stop_event
                st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
# INJECT
# ─────────────────────────────────────────────────────────────────────────────
with tab_inject:
    st.markdown('<div class="section-header">Anomaly scenario injection</div>', unsafe_allow_html=True)
    st.markdown("""
    <p style="color:#94A3B8;font-size:0.85rem;margin-bottom:1.5rem">
    Bulk-loads backdated anomaly data into Elasticsearch — agents detect it
    immediately on the next run. Each scenario targets a different service
    and failure pattern.
    </p>
    """, unsafe_allow_html=True)

    SCENARIOS = [
        {
            "key":     "ml",
            "icon":    "🧠",
            "title":   "Memory Leak",
            "service": "payment-service",
            "region":  "us-east-1",
            "desc":    "Memory climbs gradually from 55% to 89% over 25 minutes. JVM heap pressure builds until GC overhead becomes critical. Error rate begins rising above 80%.",
            "tags":    ["memory_percent", "error_rate", "HEAP_PRESSURE"],
            "fn":      inject_memory_leak,
        },
        {
            "key":     "dr",
            "icon":    "💥",
            "title":   "Deployment Rollback",
            "service": "checkout-service",
            "region":  "us-east-1",
            "desc":    "Deploy v3.5.0 completes successfully, then error rate rockets from 0.4 to 18/min within 3 minutes. NullPointerException in cart serialisation on every request.",
            "tags":    ["error_rate", "deploy_event", "INTERNAL_SERVER_ERROR"],
            "fn":      inject_deployment_rollback,
        },
        {
            "key":     "es",
            "icon":    "⚡",
            "title":   "Error Spike",
            "service": "auth-service",
            "region":  "us-west-2",
            "desc":    "Redis session cache node evicted. Auth falls back to DB lookups instantly. Error rate jumps from 0.3 to 28/min, latency spikes from 95ms to 1200ms.",
            "tags":    ["error_rate", "request_latency_ms", "CACHE_OFFLINE"],
            "fn":      inject_error_spike,
        },
    ]

    cols = st.columns(3)
    for col, s in zip(cols, SCENARIOS):
        with col:
            tags_html = " ".join(f'<span class="scenario-tag">{t}</span>' for t in s["tags"])
            st.markdown(f"""
            <div class="scenario-card">
              <div class="scenario-title">{s["icon"]} {s["title"]}</div>
              <div class="scenario-service">{s["service"]} · {s["region"]}</div>
              <div class="scenario-desc">{s["desc"]}</div>
              <div>{tags_html}</div>
            </div>
            <div style="height:0.6rem"></div>
            """, unsafe_allow_html=True)
            if st.button(f"Inject {s['title']}", key=s["key"], type="primary", use_container_width=True):
                with st.spinner(f"Injecting {s['title']}…"):
                    try:
                        s["fn"](es)
                        st.success(f"✓ {s['title']} injected — run Cassandra now.")
                    except Exception as e:
                        st.error(str(e))

# ─────────────────────────────────────────────────────────────────────────────
# PIPELINE
# ─────────────────────────────────────────────────────────────────────────────
with tab_pipeline:
    from orchestrator import (converse_stream, _write_incident, _get_es,
                               CASSANDRA_PROMPT, ARCHAEOLOGIST_PROMPT,
                               SURGEON_PROMPT, AGENT_IDS)

    st.markdown('<div class="section-header">Autonomous incident pipeline</div>', unsafe_allow_html=True)
    st.markdown("""
    <p style="color:#94A3B8;font-size:0.85rem;margin-bottom:1.5rem">
    Runs the full <strong style="color:#E2E8F0">Cassandra → Archaeologist → Surgeon</strong> chain
    via the Agent Builder streaming API. Watch each agent reason and respond in real time.
    Results are written to <code style="color:#FF6B00">incidents-quantumstate</code>.
    &nbsp;&nbsp;<strong style="color:#FBBF24">Tip:</strong> Inject a scenario first.
    </p>
    """, unsafe_allow_html=True)

    if "pr" not in st.session_state:
        st.session_state.pr = {}

    col_btn, col_clr, _ = st.columns([1, 1, 4])
    with col_btn:
        run_btn = st.button("▶  Run Pipeline", type="primary", use_container_width=True)
    with col_clr:
        if st.button("Clear", use_container_width=True, key="clr_pipe"):
            st.session_state.pr = {}
            st.rerun()

    st.markdown('<div style="height:0.8rem"></div>', unsafe_allow_html=True)

    def _stream_agent(agent_id, prompt, reasoning_slot):
        """
        Generator for st.write_stream(). Yields text chunks from the agent.
        Updates reasoning_slot with live thinking steps.
        Stores the full assembled text in a list passed by reference via closure.
        """
        collected = []
        for evt in converse_stream(agent_id, prompt):
            if evt["event"] == "reasoning":
                reasoning_slot.markdown(
                    f'<p style="color:#475569;font-size:0.76rem;font-family:'
                    f'\'JetBrains Mono\',monospace;margin:2px 0">⟳ {evt["text"]}</p>',
                    unsafe_allow_html=True,
                )
            elif evt["event"] == "message_chunk":
                collected.append(evt["text"])
                yield evt["text"]
            elif evt["event"] == "message_complete" and not collected:
                # fallback: chunks weren't sent, use complete message
                yield evt["text"]
                collected.append(evt["text"])
            elif evt["event"] == "error":
                raise RuntimeError(evt["text"])
        # stash for the caller to read back
        _stream_agent._last = "".join(collected)

    _stream_agent._last = ""

    # ── Show previous results if not re-running ───────────────────────────────
    pr = st.session_state.pr
    if pr and not run_btn:
        for key, name, role in [
            ("cassandra",     "Cassandra",     "Detection"),
            ("archaeologist", "Archaeologist", "Investigation"),
            ("surgeon",       "Surgeon",       "Remediation"),
        ]:
            out = pr.get(key, "")
            if out:
                with st.expander(f"✓  {name} — {role}", expanded=False):
                    st.code(out, language=None)

        if pr.get("incident_id"):
            st.success(f"Incident written → `incidents-quantumstate / {pr['incident_id']}`")
        if pr.get("error"):
            st.error(f"Pipeline error: {pr['error']}")

    # ── Live streaming run ────────────────────────────────────────────────────
    if run_btn:
        st.session_state.pr = {}
        cassandra_out = arch_out = surg_out = ""

        with st.status("Running incident pipeline…", expanded=True) as pipe_status:
            try:
                # ── Cassandra ─────────────────────────────────────────────────
                pipe_status.update(label="Cassandra — scanning for anomalies…")
                st.markdown(
                    '<p style="font-size:0.8rem;font-weight:600;color:#FF6B00;'
                    'margin:0 0 4px">CASSANDRA · Detection</p>',
                    unsafe_allow_html=True,
                )
                reasoning_slot = st.empty()
                st.write_stream(_stream_agent(AGENT_IDS["cassandra"], CASSANDRA_PROMPT, reasoning_slot))
                cassandra_out = _stream_agent._last
                reasoning_slot.empty()
                st.session_state.pr["cassandra"] = cassandra_out

                if "anomaly_detected: false" in cassandra_out.lower():
                    pipe_status.update(label="No anomaly detected — system is healthy", state="complete")
                    st.info("Cassandra found no anomalies. Inject a scenario and try again.")
                else:
                    # ── Archaeologist ──────────────────────────────────────────
                    st.divider()
                    pipe_status.update(label="Archaeologist — investigating root cause…")
                    st.markdown(
                        '<p style="font-size:0.8rem;font-weight:600;color:#FF6B00;'
                        'margin:0 0 4px">ARCHAEOLOGIST · Investigation</p>',
                        unsafe_allow_html=True,
                    )
                    reasoning_slot = st.empty()
                    arch_prompt = ARCHAEOLOGIST_PROMPT.format(cassandra_output=cassandra_out)
                    st.write_stream(_stream_agent(AGENT_IDS["archaeologist"], arch_prompt, reasoning_slot))
                    arch_out = _stream_agent._last
                    reasoning_slot.empty()
                    st.session_state.pr["archaeologist"] = arch_out

                    # ── Surgeon ────────────────────────────────────────────────
                    st.divider()
                    pipe_status.update(label="Surgeon — verifying recovery…")
                    st.markdown(
                        '<p style="font-size:0.8rem;font-weight:600;color:#FF6B00;'
                        'margin:0 0 4px">SURGEON · Remediation</p>',
                        unsafe_allow_html=True,
                    )
                    reasoning_slot = st.empty()
                    surg_prompt = SURGEON_PROMPT.format(
                        cassandra_output=cassandra_out,
                        archaeologist_output=arch_out,
                    )
                    st.write_stream(_stream_agent(AGENT_IDS["surgeon"], surg_prompt, reasoning_slot))
                    surg_out = _stream_agent._last
                    reasoning_slot.empty()
                    st.session_state.pr["surgeon"] = surg_out

                    # ── Write incident ─────────────────────────────────────────
                    st.divider()
                    pipe_status.update(label="Writing incident to Elasticsearch…")
                    report = {
                        "cassandra_raw":     cassandra_out,
                        "archaeologist_raw": arch_out,
                        "surgeon_raw":       surg_out,
                    }
                    for line in surg_out.splitlines():
                        for field in ("service", "anomaly_type", "root_cause", "action_taken",
                                      "resolution_status", "mttr_estimate", "lessons_learned",
                                      "pipeline_summary"):
                            if line.lower().startswith(f"- {field}:"):
                                report[field] = line.split(":", 1)[1].strip()

                    incident_id = _write_incident(_get_es(), report)
                    st.session_state.pr["incident_id"] = incident_id
                    pipe_status.update(label="Pipeline complete — incident resolved ✓", state="complete")

            except Exception as exc:
                st.session_state.pr["error"] = str(exc)
                pipe_status.update(label=f"Pipeline failed: {exc}", state="error")
                st.error(str(exc))

        st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# HEALTH
# ─────────────────────────────────────────────────────────────────────────────
with tab_health:
    st.markdown('<div class="section-header">Service health — latest values</div>', unsafe_allow_html=True)

    cols = st.columns(4)
    for col, svc in zip(cols, SERVICES):
        with col:
            mem = get_latest_metric(es, svc["name"], "memory_percent")
            cpu = get_latest_metric(es, svc["name"], "cpu_percent")
            err = get_latest_metric(es, svc["name"], "error_rate")
            lat = get_latest_metric(es, svc["name"], "request_latency_ms")

            if any([mem and mem >= 80, err and err >= 10, cpu and cpu >= 85]):
                pill = '<span class="status-pill pill-crit">CRITICAL</span>'
            elif any([mem and mem >= 65, err and err >= 3, cpu and cpu >= 65]):
                pill = '<span class="status-pill pill-warn">WARNING</span>'
            else:
                pill = '<span class="status-pill pill-ok">HEALTHY</span>'

            def row(label, value, warn, crit, suffix=""):
                cls = metric_class(value, warn, crit)
                return f"""<div class="metric-row">
                  <span class="metric-label">{label}</span>
                  <span class="metric-value {cls}">{fmt(value, suffix=suffix)}</span>
                </div>"""

            st.markdown(f"""
            <div class="metric-card">
              <div class="metric-card-title">service</div>
              <div class="metric-card-service">{svc["name"]}</div>
              <div class="metric-card-region">{svc["region"]}</div>
              {pill}
              {row("Memory",  mem,  65,  80,  "%")}
              {row("CPU",     cpu,  65,  85,  "%")}
              {row("Errors",  err,   3,  10,  "/min")}
              {row("Latency", lat, 500,1000,  "ms")}
            </div>
            """, unsafe_allow_html=True)

    # Log viewer
    st.markdown('<div style="height:1.5rem"></div>', unsafe_allow_html=True)
    st.markdown('<div class="section-header">Recent logs</div>', unsafe_allow_html=True)

    sel_col, _ = st.columns([2, 5])
    with sel_col:
        selected = st.selectbox("Service", [s["name"] for s in SERVICES], label_visibility="collapsed")

    try:
        since = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
        resp  = es.search(index="logs-quantumstate", body={
            "size": 15,
            "query": {"bool": {"filter": [
                {"term": {"service": selected}},
                {"range": {"@timestamp": {"gte": since}}},
            ]}},
            "sort": [{"@timestamp": "desc"}],
        })
        logs = [h["_source"] for h in resp["hits"]["hits"]]

        if logs:
            lines = ""
            for log in logs:
                ts    = log.get("@timestamp", "")[:19].replace("T", " ")
                level = log.get("level", "INFO")
                msg   = log.get("message", "")
                lines += f"""<div class="log-line">
                  <span class="log-ts">{ts}</span>
                  <span class="log-level level-{level}">{level}</span>
                  <span class="log-msg">{msg}</span>
                </div>"""
            st.markdown(f'<div style="background:#0D0D0D;border:1px solid #1A1A1A;border-radius:10px;padding:0.8rem 0.5rem">{lines}</div>',
                        unsafe_allow_html=True)
        else:
            st.markdown('<p style="color:#475569;font-size:0.85rem">No logs in the last 30 minutes.</p>',
                        unsafe_allow_html=True)
    except Exception as e:
        st.error(str(e))

    st.markdown('<p style="color:#334155;font-size:0.72rem;margin-top:1rem">Refresh the page to update health values.</p>',
                unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# CLEANUP
# ─────────────────────────────────────────────────────────────────────────────
with tab_cleanup:
    st.markdown('<div class="section-header">Elasticsearch index management</div>', unsafe_allow_html=True)

    try:
        all_indices = sorted([
            name for name in es.indices.get(index="*").keys()
            if not name.startswith(".")
        ])
    except Exception as e:
        st.error(str(e))
        all_indices = []

    qs_names = set(QUANTUMSTATE_INDICES.keys())
    qs_found = [i for i in all_indices if i in qs_names]
    other    = [i for i in all_indices if i not in qs_names]

    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown('<div style="color:#64748B;font-size:0.75rem;font-weight:600;text-transform:uppercase;letter-spacing:.08em;margin-bottom:.6rem">QuantumState</div>', unsafe_allow_html=True)
        if qs_found:
            for name in qs_found:
                try:    count = f"{es.count(index=name)['count']:,} docs"
                except: count = "—"
                short = name.replace("-quantumstate", "")
                st.markdown(f'<div class="idx-row idx-qs"><span class="idx-name">{short}</span><span class="idx-count">{count}</span></div>',
                            unsafe_allow_html=True)
        else:
            st.markdown('<p style="color:#475569;font-size:0.82rem">No QuantumState indices found. Run Setup first.</p>', unsafe_allow_html=True)

    with col_b:
        st.markdown('<div style="color:#64748B;font-size:0.75rem;font-weight:600;text-transform:uppercase;letter-spacing:.08em;margin-bottom:.6rem">Other</div>', unsafe_allow_html=True)
        if other:
            for name in other:
                try:    count = f"{es.count(index=name)['count']:,} docs"
                except: count = "—"
                st.markdown(f'<div class="idx-row idx-other"><span class="idx-name">{name}</span><span class="idx-count">{count}</span></div>',
                            unsafe_allow_html=True)
        else:
            st.markdown('<p style="color:#475569;font-size:0.82rem">None — cluster is clean.</p>', unsafe_allow_html=True)

    st.markdown('<div style="height:1.2rem"></div>', unsafe_allow_html=True)
    st.markdown('<div class="section-header">Actions</div>', unsafe_allow_html=True)

    btn_col1, btn_col2, btn_col3 = st.columns(3)

    with btn_col1:
        st.markdown('<p style="color:#94A3B8;font-size:0.8rem;margin-bottom:0.6rem">Remove all non-QuantumState indices.</p>', unsafe_allow_html=True)
        if st.button(
            f"Delete {len(other)} other {'index' if len(other)==1 else 'indices'}" if other else "No other indices",
            type="primary", use_container_width=True, disabled=len(other)==0, key="del_other"
        ):
            deleted, failed = [], []
            for name in other:
                try:
                    es.indices.delete(index=name)
                    deleted.append(name)
                except Exception as e:
                    failed.append(f"{name} ({e})")
            if deleted: st.success(f"Deleted: {', '.join(deleted)}")
            if failed:  st.error(f"Failed: {', '.join(failed)}")
            st.rerun()

    with btn_col2:
        st.markdown('<p style="color:#94A3B8;font-size:0.8rem;margin-bottom:0.6rem">Wipe QuantumState data only — keeps indices, clears all documents.</p>', unsafe_allow_html=True)
        if st.button("Clear QuantumState Data", use_container_width=True,
                     disabled=len(qs_found)==0, key="clear_qs"):
            cleared, failed = [], []
            for name in qs_found:
                try:
                    es.delete_by_query(index=name, body={"query": {"match_all": {}}}, refresh=True)
                    cleared.append(name.replace("-quantumstate", ""))
                except Exception as e:
                    failed.append(f"{name} ({e})")
            if cleared: st.success(f"Cleared: {', '.join(cleared)}")
            if failed:  st.error(f"Failed: {', '.join(failed)}")
            st.rerun()

    with btn_col3:
        st.markdown('<p style="color:#94A3B8;font-size:0.8rem;margin-bottom:0.6rem">Full reset — deletes QuantumState indices entirely. Re-run Setup after.</p>', unsafe_allow_html=True)
        if st.button("Delete QuantumState Indices", use_container_width=True,
                     disabled=len(qs_found)==0, key="del_qs"):
            deleted, failed = [], []
            for name in qs_found:
                try:
                    es.indices.delete(index=name)
                    deleted.append(name.replace("-quantumstate", ""))
                except Exception as e:
                    failed.append(f"{name} ({e})")
            if deleted: st.success(f"Deleted indices: {', '.join(deleted)} — run Setup to recreate.")
            if failed:  st.error(f"Failed: {', '.join(failed)}")
            st.rerun()
