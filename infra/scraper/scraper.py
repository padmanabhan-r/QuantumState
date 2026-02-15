"""
QuantumState — Metrics Scraper
Polls /health on each service container every 15s,
writes real readings to metrics-quantumstate in Elasticsearch.
Falls back to synthetic values if a container is unreachable.
"""
import os
import time
import random
import datetime
import requests
from elasticsearch import Elasticsearch
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

# --- Elastic client ---
es = Elasticsearch(
    cloud_id=os.getenv("ELASTIC_CLOUD_ID"),
    api_key=os.getenv("ELASTIC_API_KEY"),
)

SCRAPE_INTERVAL = int(os.getenv("SCRAPE_INTERVAL_SECONDS", "15"))

SERVICES = [
    {"name": "payment-service",   "url": os.getenv("PAYMENT_SERVICE_URL",   "http://payment-service:8001")},
    {"name": "checkout-service",  "url": os.getenv("CHECKOUT_SERVICE_URL",  "http://checkout-service:8002")},
    {"name": "auth-service",      "url": os.getenv("AUTH_SERVICE_URL",      "http://auth-service:8003")},
    {"name": "inventory-service", "url": os.getenv("INVENTORY_SERVICE_URL", "http://inventory-service:8004")},
]

REGIONS = {
    "payment-service":   "us-east-1",
    "checkout-service":  "us-east-1",
    "auth-service":      "eu-west-1",
    "inventory-service": "us-west-2",
}

INDEX = "metrics-quantumstate"


def _synthetic_fallback(service: str) -> dict:
    """Return plausible synthetic metrics when a container is unreachable."""
    return {
        "memory_percent": round(random.uniform(40, 60), 2),
        "cpu_percent":    round(random.uniform(10, 30), 2),
        "error_rate":     round(random.uniform(0, 0.8), 2),
        "latency_ms":     round(random.uniform(50, 150), 1),
        "source":         "synthetic",
    }


def scrape_service(svc: dict) -> dict | None:
    try:
        resp = requests.get(f"{svc['url']}/health", timeout=5)
        resp.raise_for_status()
        data = resp.json()
        return {
            "memory_percent": data.get("memory_percent", 0),
            "cpu_percent":    data.get("cpu_percent", 0),
            "error_rate":     data.get("error_rate", 0),
            "latency_ms":     data.get("latency_ms", 0),
            "source":         "real",
        }
    except Exception as e:
        print(f"[scraper] {svc['name']} unreachable ({e}) — using synthetic fallback")
        return _synthetic_fallback(svc["name"])


def write_metrics(service: str, region: str, metrics: dict):
    ts = datetime.datetime.utcnow().isoformat() + "Z"
    for metric_type, value in [
        ("memory_percent", metrics["memory_percent"]),
        ("cpu_percent",    metrics["cpu_percent"]),
        ("error_rate",     metrics["error_rate"]),
        ("latency_ms",     metrics["latency_ms"]),
    ]:
        doc = {
            "@timestamp":  ts,
            "service":     service,
            "region":      region,
            "metric_type": metric_type,
            "value":       value,
            "source":      metrics.get("source", "real"),
        }
        es.index(index=INDEX, document=doc)
    print(f"[scraper] {service} | mem={metrics['memory_percent']}% cpu={metrics['cpu_percent']}% err={metrics['error_rate']} lat={metrics['latency_ms']}ms [{metrics['source']}]")


def run():
    print(f"[scraper] Starting — interval={SCRAPE_INTERVAL}s, services={[s['name'] for s in SERVICES]}")
    while True:
        for svc in SERVICES:
            metrics = scrape_service(svc)
            write_metrics(svc["name"], REGIONS[svc["name"]], metrics)
        time.sleep(SCRAPE_INTERVAL)


if __name__ == "__main__":
    run()
