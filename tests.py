#!/usr/bin/env python3
"""Smoke tests for MemEngine — run against a temp DB, verifies every command."""
import json, os, subprocess, sys, tempfile

MEM = os.path.join(os.path.dirname(__file__), "mem.py")
BANK = "test"
passed, failed = 0, 0


def run(*args):
    r = subprocess.run([sys.executable, MEM, *args], capture_output=True, text=True,
                       env={**os.environ, "MEMENGINE_DB": DB})
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        raise AssertionError(f"non-JSON output: {r.stdout!r} stderr={r.stderr!r}")


DB = tempfile.mkdtemp() + "/test.db"
os.environ["MEMENGINE_DB"] = DB


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✓ {name}")
    else:
        failed += 1
        print(f"  ✗ {name} {detail}")


# --- add ---
r = run("add", BANK, "fact", "RPC endpoint is https://rpc.test.live chainId 99901", "--tags", "rpc")
check("add fact", r["ok"] and r["type"] == "fact")
fid = r["id"]

r = run("add", BANK, "experience", "Deploy script replaced every config file; restored from git", "--tags", "lesson")
check("add experience", r["ok"])
eid = r["id"]

# duplicate guard
r = run("add", BANK, "fact", "RPC endpoint is https://rpc.test.live chainId 99901", "--tags", "rpc")
check("duplicate blocked", r["ok"] is False and r.get("duplicate") is True)
r = run("add", BANK, "fact", "RPC endpoint is https://rpc.test.live chainId 99901 v2 unique suffix", "--force")
check("force bypass", r["ok"])

# observation must not be addable
r = run("add", BANK, "observation", "cheating")
check("observe-via-add blocked", r["ok"] is False)

# --- observe + refs ---
r = run("add", BANK, "experience", "Second deploy also clobbered configs", "--tags", "lesson")
r = run("add", BANK, "experience", "Third deploy clobbered configs again", "--tags", "lesson")
e2, e3 = r["id"] - 1, r["id"]
r = run("observe", BANK, "Deploys clobber configs; always snapshot before deploy", "--refs", f"{eid},{e2},{e3}")
check("observe with refs", r["ok"] and r["type"] == "observation" and sorted(r["links_added"]) == sorted([eid, e2, e3]))
oid = r["id"]

# --- recall: observation ranks first, multi-term ---
r = run("recall", BANK, "deploy configs")
check("recall multi-term finds results", r["count"] >= 2)
check("observation ranked first", r["results"][0]["type"] == "observation")

# weird chars sanitized
r = run("recall", BANK, "deploy (configs)!!")
check("weird chars handled", r["ok"])

# type filter
r = run("recall", BANK, "deploy", "--type", "observation")
check("recall type filter", r["count"] == 1 and r["results"][0]["type"] == "observation")

# --- link / backlinks ---
r = run("link", BANK, str(oid), str(fid))
check("link", r["ok"])
r = run("link", BANK, str(oid), str(fid))
check("duplicate link blocked", r["ok"] is False)
r = run("backlinks", BANK, str(fid))
check("backlinks", r["count"] >= 1 and r["referenced_by"][0]["id"] == oid)

# self-link blocked
r = run("link", BANK, str(fid), str(fid))
check("self-link blocked", r["ok"] is False)

# --- graph ---
r = run("graph", BANK)
check("graph nodes/edges", r["nodes"] >= 5 and r["edges"] >= 2)

# --- stats / banks ---
r = run("stats", BANK)
check("stats health", r["total"] >= 5 and r["by_type"].get("observation") == 1 and "learning" in r["health"])
r = run("banks")
check("banks listed", any(b["bank"] == BANK for b in r["banks"]))

# --- list / delete ---
r = run("list", BANK, "--limit", "3")
check("list limit", len(r["memories"]) == 3)
r = run("delete", BANK, str(e3))
check("delete", r["ok"])
r = run("backlinks", BANK, str(oid))
check("delete cleans links", all(m["id"] != e3 for m in r["referenced_by"]))
r = run("delete", BANK, "99999")
check("delete missing errors", r["ok"] is False)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
