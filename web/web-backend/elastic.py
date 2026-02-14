"""Shared Elasticsearch client — reads .env from project root or local."""
import os
from elasticsearch import Elasticsearch
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

API_KEY     = os.getenv("ELASTIC_API_KEY", "")
ELASTIC_URL = os.getenv("ELASTIC_URL", "").rstrip("/")


def get_es() -> Elasticsearch:
    cloud_id = os.getenv("ELASTIC_CLOUD_ID")
    if cloud_id:
        return Elasticsearch(cloud_id=cloud_id, api_key=API_KEY, request_timeout=15)
    return Elasticsearch(ELASTIC_URL, api_key=API_KEY, request_timeout=15)
