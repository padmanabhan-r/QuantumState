"""Compares setup_agents.py definitions against the live Kibana cloud state."""
import os, sys, requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

# ── Load definitions from setup_agents.py ────────────────────────────────────
globs = {"__file__": str(Path(__file__).parent / "setup_agents.py"), "__name__": "not_main"}
src = (Path(__file__).parent / "setup_agents.py").read_text()
exec(compile(src.replace("if __name__ == '__main__':", "if False:"), "setup_agents.py", "exec"), globs)

script_tools  = {t["id"]: t for t in globs["TOOLS"] + [globs["WORKFLOW_TOOL"]]}
script_agents = {a["id"]: a for a in globs["_build_agents"]()}

# ── Kibana connection ─────────────────────────────────────────────────────────
kibana_url = globs["KIBANA_URL"]
api_key    = globs["API_KEY"]
headers    = {"Authorization": f"ApiKey {api_key}", "Content-Type": "application/json"}

# ── Tools ─────────────────────────────────────────────────────────────────────
r = requests.get(f"{kibana_url}/api/agent_builder/tools", headers=headers, timeout=30)
cloud_tools = {t["id"]: t for t in r.json().get("results", []) if t.get("type") != "builtin"}

print("=== TOOL COMPARISON ===")
diffs = 0
for tid in sorted(set(list(script_tools) + list(cloud_tools))):
    if tid not in script_tools:
        print(f"  MISSING FROM SCRIPT : {tid}")
        diffs += 1
    elif tid not in cloud_tools:
        print(f"  MISSING FROM CLOUD  : {tid}")
        diffs += 1
    else:
        issues = []
        sd = script_tools[tid].get("description", "").strip()
        cd = cloud_tools[tid].get("description", "").strip()
        if sd != cd:
            issues.append("description differs")
        sq = script_tools[tid].get("configuration", {}).get("query", "").strip()
        cq = cloud_tools[tid].get("configuration", {}).get("query", "").strip()
        if sq != cq:
            sl, cl = sq.splitlines(), cq.splitlines()
            for i, (a, b) in enumerate(zip(sl, cl)):
                if a.strip() != b.strip():
                    issues.append(f"query differs at line {i+1}")
                    issues.append(f"  SCRIPT: {repr(a.strip())}")
                    issues.append(f"  CLOUD:  {repr(b.strip())}")
                    break
            else:
                if len(sl) != len(cl):
                    issues.append(f"query line count: script={len(sl)} cloud={len(cl)}")
        if issues:
            print(f"  DIFF  {tid}")
            for i in issues: print(f"        {i}")
            diffs += 1
        else:
            print(f"  OK    {tid}")

# ── Agents ────────────────────────────────────────────────────────────────────
r2 = requests.get(f"{kibana_url}/api/agent_builder/agents", headers=headers, timeout=30)
cloud_agents = {a["id"]: a for a in r2.json().get("results", []) if a["id"] in script_agents}

print("\n=== AGENT COMPARISON ===")
for aid in script_agents:
    sa = script_agents[aid]
    ca = cloud_agents.get(aid)
    if not ca:
        print(f"  MISSING FROM CLOUD: {aid}")
        diffs += 1
        continue
    issues = []
    si = sa.get("configuration", {}).get("instructions", "").strip()
    ci = ca.get("configuration", {}).get("instructions", "").strip()
    if si != ci:
        sl, cl = si.splitlines(), ci.splitlines()
        for i, (a, b) in enumerate(zip(sl, cl)):
            if a != b:
                issues.append(f"instructions differ at line {i+1}")
                issues.append(f"  SCRIPT: {repr(a)}")
                issues.append(f"  CLOUD:  {repr(b)}")
                break
        else:
            issues.append(f"instructions line count: script={len(sl)} cloud={len(cl)}")
    st = sorted(sa["configuration"]["tools"][0]["tool_ids"])
    ct = sorted((ca.get("configuration", {}).get("tools") or [{}])[0].get("tool_ids", []))
    if st != ct:
        only_s = sorted(set(st) - set(ct))
        only_c = sorted(set(ct) - set(st))
        if only_s: issues.append(f"only in script: {only_s}")
        if only_c: issues.append(f"only in cloud:  {only_c}")
    sc = sa.get("avatar_color", "")
    cc = ca.get("avatar_color", "")
    if sc.lower() != cc.lower():
        issues.append(f"colour: script={sc}  cloud={cc}")
    if issues:
        print(f"  DIFF  {aid}")
        for i in issues: print(f"        {i}")
        diffs += 1
    else:
        print(f"  OK    {aid}")

print(f"\n{'✅ Fully in sync — no differences found.' if diffs == 0 else f'⚠  {diffs} difference(s) found.'}")
