"""Read-only MCP server for the claim ledger. No writes. No credentials.

Tools:
  list_systems   what was mined
  get_claim      one claim plus its sources
  pending_tags   the proposed tags, still waiting on a person
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import ledger  # noqa: E402


def handle(req: dict) -> dict:
    method = req.get("method")
    _id = req.get("id")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": _id, "result": {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}, "serverInfo": {"name": "portfolio-from-evidence", "version": "0.1.0"}}}
    if method == "notifications/initialized":
        return {}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": _id, "result": {"tools": [
            {"name": "list_systems", "description": "List the six evidence systems and how many records each holds.", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "get_claim", "description": "Return one claim and the sources the miner attached to it.", "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]}},
            {"name": "pending_tags", "description": "Proposed tags. These are not public until a person runs approve --yes.", "inputSchema": {"type": "object", "properties": {}}},
        ]}}
    if method == "tools/call":
        name = req["params"]["name"]
        args = req["params"].get("arguments") or {}
        if name == "list_systems":
            counts = {}
            for rec in ledger.load_corpus():
                counts[rec["system"]] = counts.get(rec["system"], 0) + 1
            text = json.dumps(counts, indent=2)
        elif name == "get_claim":
            seed = ledger.load_json(ledger.DATA / "claims.json")
            claim = next((c for c in seed["claims"] if c["id"] == args.get("id")), None)
            if not claim:
                text = f"unknown claim {args.get('id')}"
            else:
                proposal = ledger.mine([claim], ledger.load_corpus())
                text = json.dumps(proposal["claims"][0], indent=2)
        elif name == "pending_tags":
            path = ledger.OUT / "pending.json"
            text = path.read_text() if path.exists() else "no pending.json — run python3 ledger.py mine"
        else:
            return {"jsonrpc": "2.0", "id": _id, "error": {"code": -32601, "message": name}}
        return {"jsonrpc": "2.0", "id": _id, "result": {"content": [{"type": "text", "text": text}]}}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": _id, "result": {}}
    return {"jsonrpc": "2.0", "id": _id, "error": {"code": -32601, "message": method or "missing method"}}


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        req = json.loads(line)
        resp = handle(req)
        if resp:
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
