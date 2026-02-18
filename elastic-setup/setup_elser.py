"""
QuantumState — ELSER Inference Endpoint Setup

Deploys the ELSER v2 sparse embedding model on Elastic Cloud.
This must run ONCE before setup_agents.py or sim setup, because the
incidents-quantumstate and runbooks-quantumstate indices use
semantic_text fields that require this inference endpoint.

Usage:
    python elastic-setup/setup_elser.py

Requirements:
    .env must contain:
        ELASTIC_CLOUD_ID — your Elastic Cloud ID
        ELASTIC_API_KEY  — API key with inference privileges
"""

import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv
from elasticsearch import Elasticsearch

load_dotenv(Path(__file__).parent.parent / ".env")

ELASTIC_API_KEY = os.getenv("ELASTIC_API_KEY", "")
ELASTIC_CLOUD_ID = os.getenv("ELASTIC_CLOUD_ID", "")
ELASTIC_URL = os.getenv("ELASTIC_URL", "").rstrip("/")

ELSER_INFERENCE_ID = ".elser-2-elasticsearch"
ELSER_MODEL_ID = ".elser_model_2"


def get_es() -> Elasticsearch:
    if ELASTIC_CLOUD_ID:
        return Elasticsearch(
            cloud_id=ELASTIC_CLOUD_ID,
            api_key=ELASTIC_API_KEY,
            request_timeout=60,
        )
    return Elasticsearch(ELASTIC_URL, api_key=ELASTIC_API_KEY, request_timeout=60)


def setup_elser():
    print("\n🔍 QuantumState — ELSER Inference Endpoint Setup\n")

    if not ELASTIC_API_KEY:
        sys.exit("ERROR: ELASTIC_API_KEY not set in .env")
    if not ELASTIC_CLOUD_ID and not ELASTIC_URL:
        sys.exit("ERROR: Set ELASTIC_CLOUD_ID or ELASTIC_URL in .env")

    es = get_es()

    # Check if already deployed
    try:
        existing = es.inference.get(inference_id=ELSER_INFERENCE_ID)
        print(f"✅ ELSER endpoint already exists: {ELSER_INFERENCE_ID}")
        print("   Nothing to do — endpoint is ready.\n")
        return
    except Exception:
        pass  # Not found — create it

    print(f"Deploying ELSER model: {ELSER_MODEL_ID}")
    print(f"Inference endpoint ID: {ELSER_INFERENCE_ID}")
    print()

    # Create the ELSER sparse embedding inference endpoint
    try:
        es.inference.put(
            task_type="sparse_embedding",
            inference_id=ELSER_INFERENCE_ID,
            body={
                "service": "elasticsearch",
                "service_settings": {
                    "num_allocations": 1,
                    "num_threads": 1,
                    "model_id": ELSER_MODEL_ID,
                },
            },
        )
        print("✅ Inference endpoint created.")
    except Exception as exc:
        sys.exit(f"ERROR creating inference endpoint: {exc}")

    # Wait for model to be ready
    print("   Waiting for model allocation (this can take 30–90 seconds)...")
    deadline = time.time() + 120
    while time.time() < deadline:
        try:
            info = es.inference.get(inference_id=ELSER_INFERENCE_ID)
            # If we can retrieve it without error, it's allocated
            print("✅ ELSER model allocated and ready.\n")
            return
        except Exception:
            pass
        time.sleep(5)
        print("   .", end="", flush=True)

    print()
    print("⚠  Model allocation timed out after 120s.")
    print("   It may still be loading in the background. Check Kibana > Machine Learning > Trained Models.")
    print("   Once allocated, continue with: python elastic-setup/setup_agents.py\n")


if __name__ == "__main__":
    setup_elser()
