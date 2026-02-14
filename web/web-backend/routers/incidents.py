"""GET /api/incidents — last 20 incidents from incidents-quantumstate."""
from fastapi import APIRouter
from elastic import get_es

router = APIRouter(tags=["incidents"])


@router.get("/incidents")
def get_incidents():
    es = get_es()
    try:
        resp = es.search(
            index="incidents-quantumstate*",
            body={
                "size": 20,
                "sort": [{"@timestamp": {"order": "desc"}}],
                "query": {"match_all": {}},
                "_source": [
                    "@timestamp", "service", "anomaly_type",
                    "resolution_status", "mttr_estimate", "root_cause",
                    "action_taken", "pipeline_summary",
                ],
            },
        )
        hits = resp["hits"]["hits"]
        incidents = [{"id": h["_id"], **h["_source"]} for h in hits]
        return {"incidents": incidents, "total": len(incidents)}
    except Exception as exc:
        return {"incidents": [], "total": 0, "error": str(exc)}


@router.get("/incidents/stats")
def get_incident_stats():
    """MTTR stats for today."""
    es = get_es()
    try:
        resp = es.search(
            index="incidents-quantumstate*",
            body={
                "size": 0,
                "query": {"range": {"@timestamp": {"gte": "now-24h"}}},
                "aggs": {
                    "resolved_count": {
                        "filter": {"term": {"resolution_status": "RESOLVED"}}
                    },
                    "avg_mttr_raw": {
                        "filter": {
                            "bool": {
                                "must": [
                                    {"exists": {"field": "mttr_seconds"}}
                                ]
                            }
                        },
                        "aggs": {
                            "avg": {"avg": {"field": "mttr_seconds"}}
                        },
                    },
                },
            },
        )
        aggs = resp["aggregations"]
        total = resp["hits"]["total"]["value"]
        resolved = aggs["resolved_count"]["doc_count"]
        avg_mttr = aggs["avg_mttr_raw"]["avg"].get("value") or 0
        return {
            "incidents_today": total,
            "resolved_today": resolved,
            "avg_mttr_seconds": round(avg_mttr),
            "manual_baseline_seconds": 2820,  # 47 min manual baseline
        }
    except Exception as exc:
        return {
            "incidents_today": 0,
            "resolved_today": 0,
            "avg_mttr_seconds": 0,
            "manual_baseline_seconds": 2820,
            "error": str(exc),
        }
