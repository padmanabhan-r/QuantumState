"""POST /api/chat — proxy to Agent Builder converse (sync)."""
import os
import json
import requests
from fastapi import APIRouter
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env"))

router = APIRouter(tags=["chat"])

API_KEY    = os.getenv("ELASTIC_API_KEY", "")
KIBANA_URL = ""


def _get_kibana_url() -> str:
    global KIBANA_URL
    if KIBANA_URL:
        return KIBANA_URL
    explicit = os.getenv("KIBANA_URL", "").strip().rstrip("/")
    if explicit:
        KIBANA_URL = explicit
        return KIBANA_URL
    cloud_id = os.getenv("ELASTIC_CLOUD_ID", "")
    if cloud_id:
        try:
            import base64
            _, encoded = cloud_id.split(":", 1)
            decoded = base64.b64decode(encoded + "==").decode("utf-8")
            parts = decoded.rstrip("\x00").split("$")
            if len(parts) >= 3:
                KIBANA_URL = f"https://{parts[2]}.{parts[0]}"
            elif len(parts) == 2:
                KIBANA_URL = f"https://{parts[1]}.{parts[0]}"
        except Exception:
            pass
    return KIBANA_URL


AGENT_IDS = {
    "cassandra":     "cassandra-detection-agent",
    "archaeologist": "archaeologist-investigation-agent",
    "surgeon":       "surgeon-action-agent",
    "guardian":      "guardian-verification-agent",
}


class ChatRequest(BaseModel):
    agent_id: str
    message: str


@router.post("/chat")
def chat(req: ChatRequest):
    kibana = _get_kibana_url()
    if not kibana:
        return {"error": "KIBANA_URL not configured"}

    agent_id = AGENT_IDS.get(req.agent_id, req.agent_id)
    url = f"{kibana}/api/agent_builder/converse"
    headers = {
        "Authorization": f"ApiKey {API_KEY}",
        "kbn-xsrf": "true",
        "Content-Type": "application/json",
    }
    payload = {"agent_id": agent_id, "input": req.message}

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        response_text = (
            data.get("output")
            or data.get("message_content")
            or data.get("response")
            or json.dumps(data)
        )
        return {"response": response_text, "agent": req.agent_id}
    except Exception as exc:
        return {"error": str(exc), "agent": req.agent_id}
