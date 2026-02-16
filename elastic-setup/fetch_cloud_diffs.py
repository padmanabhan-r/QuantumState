import os, requests
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

kibana_url = os.getenv("KIBANA_URL","").strip().rstrip("/")
api_key = os.getenv("ELASTIC_API_KEY","")
headers = {"Authorization": f"ApiKey {api_key}", "Content-Type": "application/json"}

print("Kibana:", kibana_url)

r = requests.get(f"{kibana_url}/api/agent_builder/tools/detect_memory_leak", headers=headers, timeout=30)
print("\n=== detect_memory_leak description ===")
print(repr(r.json().get("description","")))

r2 = requests.get(f"{kibana_url}/api/agent_builder/agents/surgeon-action-agent", headers=headers, timeout=30)
print("\n=== Surgeon instructions ===")
print(r2.json().get("configuration",{}).get("instructions",""))

r3 = requests.get(f"{kibana_url}/api/agent_builder/agents/guardian-verification-agent", headers=headers, timeout=30)
instr = r3.json().get("configuration",{}).get("instructions","")
print("\n=== Guardian latency lines ===")
for i, line in enumerate(instr.splitlines()):
    if "latency" in line.lower():
        print(f"  line {i+1}: {repr(line)}")

r4 = requests.get(f"{kibana_url}/api/agent_builder/agents/cassandra-detection-agent", headers=headers, timeout=30)
instr4 = r4.json().get("configuration",{}).get("instructions","")
print("\n=== Cassandra last 3 lines ===")
for line in instr4.splitlines()[-3:]:
    print(repr(line))
