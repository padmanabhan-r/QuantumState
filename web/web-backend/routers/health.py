"""GET /api/health — last 5-min avg metrics per service."""
from fastapi import APIRouter
from elastic import get_es

router = APIRouter(tags=["health"])


@router.get("/health")
def get_health():
    es = get_es()
    try:
        resp = es.search(
            index="metrics-quantumstate*",
            body={
                "size": 0,
                "query": {"range": {"@timestamp": {"gte": "now-5m"}}},
                "aggs": {
                    "by_service": {
                        "terms": {"field": "service", "size": 20},
                        "aggs": {
                            "avg_cpu":    {"avg": {"field": "cpu_percent"}},
                            "avg_memory": {"avg": {"field": "memory_percent"}},
                            "avg_error":  {"avg": {"field": "error_rate"}},
                            "avg_latency":{"avg": {"field": "latency_ms"}},
                        },
                    }
                },
            },
        )
        buckets = resp["aggregations"]["by_service"]["buckets"]
        services = []
        for b in buckets:
            def _v(key):
                val = b.get(key, {}).get("value")
                return round(val, 2) if val is not None else None

            services.append({
                "service":        b["key"],
                "cpu_percent":    _v("avg_cpu"),
                "memory_percent": _v("avg_memory"),
                "error_rate":     _v("avg_error"),
                "latency_ms":     _v("avg_latency"),
            })
        return {"services": services}
    except Exception as exc:
        return {"services": [], "error": str(exc)}
