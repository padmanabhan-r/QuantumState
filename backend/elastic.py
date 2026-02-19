"""Shared Elasticsearch client — reads .env from project root or local."""
import os
from elasticsearch import Elasticsearch
from dotenv import load_dotenv
from creds import get_creds

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

API_KEY     = os.getenv("ELASTIC_API_KEY", "")
ELASTIC_URL = os.getenv("ELASTIC_URL", "").rstrip("/")


def get_es(timeout: int = 15) -> Elasticsearch:
    override = get_creds()
    cloud_id = override.get("cloud_id") or os.getenv("ELASTIC_CLOUD_ID")
    api_key  = override.get("api_key")  or API_KEY
    if cloud_id:
        return Elasticsearch(cloud_id=cloud_id, api_key=api_key, request_timeout=timeout)
    return Elasticsearch(ELASTIC_URL, api_key=api_key, request_timeout=timeout)
