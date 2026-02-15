"""
Deploy QuantumState remediation workflow to Kibana.

Usage:
    python elastic-setup/workflows/deploy_workflow.py

Reads ELASTIC_API_KEY and KIBANA_URL (or ELASTIC_CLOUD_ID) from .env
"""

import os
import sys
import json
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")


def _derive_kibana_url() -> str:
    explicit = os.getenv("KIBANA_URL", "").strip().rstrip("/")
    if explicit:
        return explicit
    cloud_id = os.getenv("ELASTIC_CLOUD_ID", "")
    if not cloud_id:
        return ""
    try:
        import base64
        _, encoded = cloud_id.split(":", 1)
        decoded = base64.b64decode(encoded + "==").decode("utf-8")
        parts = decoded.rstrip("\x00").split("$")
        if len(parts) >= 3:
            return f"https://{parts[2]}.{parts[0]}"
        elif len(parts) == 2:
            return f"https://{parts[1]}.{parts[0]}"
    except Exception:
        pass
    return ""


def deploy_workflow(yaml_path: str) -> dict:
    kibana_url = _derive_kibana_url()
    api_key = os.getenv("ELASTIC_API_KEY", "")

    if not kibana_url:
        print("ERROR: Could not determine Kibana URL. Set KIBANA_URL or ELASTIC_CLOUD_ID in .env")
        sys.exit(1)
    if not api_key:
        print("ERROR: ELASTIC_API_KEY not set in .env")
        sys.exit(1)

    with open(yaml_path, "r") as f:
        yaml_content = f.read()

    url = f"{kibana_url}/api/workflows"
    headers = {
        "kbn-xsrf": "true",
        "x-elastic-internal-origin": "Kibana",
        "Content-Type": "application/json",
        "Authorization": f"ApiKey {api_key}",
    }

    print(f"Deploying workflow to: {url}")
    resp = requests.post(url, headers=headers, json={"yaml": yaml_content}, timeout=30)

    if resp.ok:
        data = resp.json()
        print(f"✅ Deployed: {data.get('name', 'Unknown')}")
        print(f"   ID: {data.get('id', 'Unknown')}")
        print(f"\nAdd this to your .env file:")
        print(f"   REMEDIATION_WORKFLOW_ID={data.get('id', '')}")
        return data
    else:
        print(f"❌ Deploy failed: {resp.status_code}")
        try:
            print(f"   {json.dumps(resp.json(), indent=2)}")
        except Exception:
            print(f"   {resp.text[:500]}")
        sys.exit(1)


if __name__ == "__main__":
    yaml_path = Path(__file__).parent / "remediation-workflow.yaml"
    deploy_workflow(str(yaml_path))
