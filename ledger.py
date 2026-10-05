"""Claim ledger: mine six systems, propose a tag, wait for a person, publish the misses.

No dependencies. Risky writes (anything that changes a claim's public status) wait
behind an approval file. Reads and dry-runs never wait.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
SYSTEMS = DATA / "systems"
OUT = ROOT / "out"
GOLD = DATA / "gold.json"

STOP = {
    "a", "an", "the", "of", "to", "in", "on", "for", "and", "or", "i", "we", "my",
    "our", "is", "was", "that", "this", "from", "about", "with", "as", "at", "by",
    "it", "be", "are", "been", "since", "into", "over", "than", "then",
}

TAGS = ("verified", "flagged", "estimate", "retire")


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")


def tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+(?:'[a-z]+)?", text.lower())
    return {w for w in words if w not in STOP and len(w) > 1}


def numbers(text: str) -> list[str]:
    found = re.findall(r"\d+(?:\.\d+)?%?", text.replace(",", ""))
    out = []
    for n in found:
        out.append(n)
        if n.endswith("%"):
            out.append(n[:-1])
    return out


def load_corpus() -> list[dict]:
    rows = []
    for path in sorted(SYSTEMS.glob("*.json")):
        blob = load_json(path)
        system = blob["system"]
        for rec in blob["records"]:
            rec = dict(rec)
            rec["system"] = system
            rec["blob"] = f"{rec.get('title', '')} {rec.get('body', '')}"
            rows.append(rec)
    return rows


def quote_window(text: str, needle: str, radius: int = 90) -> str:
    low = text.lower()
    i = low.find(needle.lower())
    if i < 0:
        return text[: 2 * radius].strip()
    start = max(0, i - radius)
    end = min(len(text), i + len(needle) + radius)
    chunk = text[start:end].strip()
    if start:
        chunk = "…" + chunk
    if end < len(text):
        chunk = chunk + "…"
    return re.sub(r"\s+", " ", chunk)


def score_record(claim: dict, rec: dict) -> dict | None:
    ctok = tokens(claim["text"])
    rtok = tokens(rec["blob"])
    overlap = ctok & rtok
    cnums = numbers(claim["text"])
    rnums = numbers(rec["blob"])
    num_hit = [n for n in cnums if n in rnums]
    if not overlap and not num_hit:
        return None
    weight = len(overlap) + 2 * len(num_hit)
    if rec["system"] in {"tickets", "documents", "git", "meetings"}:
        weight += 1
    if rec["system"] == "chat":
        weight -= 1
    if weight < 3 and not num_hit:
        return None
    if weight < 2:
        return None
    return {
        "system": rec["system"],
        "id": rec["id"],
        "date": rec.get("date"),
        "overlap": sorted(overlap),
        "numbers": num_hit,
        "weight": weight,
        "quote": quote_window(rec["blob"], (num_hit or list(overlap) or ["."])[0]),
        "blob": rec["blob"],
    }


def decide(claim: dict, hits: list[dict]) -> dict:
    hits = sorted(hits, key=lambda h: h["weight"], reverse=True)
    blobs = " ".join(h["blob"].lower() for h in hits)
    systems = {h["system"] for h in hits}
    proposed = {
        "id": claim["id"],
        "text": claim["text"],
        "used_as": claim.get("used_as"),
        "prior_status": claim.get("status", "pending"),
        "sources": [{k: h[k] for k in ("system", "id", "date", "quote", "numbers")} for h in hits[:4]],
        "rewrite": None,
        "why": "",
        "tag": "flagged",
        "confidence": 0.4,
    }
    if not hits:
        proposed["why"] = "No source mentioned this claim. Do not publish it until one does."
        proposed["tag"] = "flagged"
        return proposed

    growth = bool(re.search(r"\d+%\s+since|grew|growth|increased", claim["text"].lower()))
    if growth and re.search(r"not (year-over-year )?growth|count of current|not a (growth|percentage)", blobs):
        proposed["tag"] = "retire"
        proposed["confidence"] = 0.86
        proposed["why"] = (
            "The number exists, but the source says it is a snapshot count, not growth. "
            "Publishing it as a percentage increase would be a different claim."
        )
        n = next((x for h in hits for x in h["numbers"] if not x.endswith("%")), None)
        proposed["rewrite"] = (
            f"Say {n} open items, a snapshot count, not year-over-year growth."
            if n else "Report the snapshot count, not a growth rate."
        )
        return proposed

    number_blobs = " ".join(h["blob"].lower() for h in hits if h["numbers"])
    if re.search(r"not a production|in our testing|notebook result|not shipped", number_blobs):
        proposed["tag"] = "estimate"
        proposed["confidence"] = 0.8
        proposed["why"] = "The number is real in a test or notebook, not in production. Keep the assumption visible."
        proposed["rewrite"] = re.sub(
            r"in production\.?$",
            "in our testing, on this dataset — not a production metric.",
            claim["text"],
            flags=re.I,
        )
        return proposed

    claim_nums = numbers(claim["text"])
    auth_with_num = [h for h in hits if h["system"] in {"tickets", "documents", "git", "meetings"} and h["numbers"]]
    informal_with_num = [h for h in hits if h["system"] in {"chat"} and h["numbers"]]
    caution = re.search(r"do not quote|sign-in sheet is the source|i think|\?\?", blobs)

    if claim_nums and informal_with_num and not auth_with_num:
        proposed["tag"] = "flagged"
        proposed["confidence"] = 0.55
        proposed["why"] = (
            "The number only shows up in chat. A roster, ticket, or signed-in count would be enough to publish; a guess is not."
        )
        if caution:
            proposed["why"] += " A more careful source also says not to quote it."
        return proposed

    if auth_with_num or (not claim_nums and len({h["system"] for h in hits if h["system"] != "chat"}) >= 2):
        proposed["tag"] = "verified"
        proposed["confidence"] = min(0.93, 0.62 + 0.08 * len({h["system"] for h in hits}))
        proposed["why"] = "Independent records agree on the fact and the number."
        return proposed

    proposed["why"] = "Some overlap, not enough to publish. Flagged for a person."
    return proposed


def mine(claims: list[dict], corpus: list[dict]) -> dict:
    rows = []
    for claim in claims:
        hits = [h for rec in corpus if (h := score_record(claim, rec))]
        rows.append(decide(claim, hits))
    return {
        "generated": date.today().isoformat(),
        "policy": "Approve the risky writes. Reads and dry-runs never wait.",
        "counts": {tag: sum(1 for r in rows if r["tag"] == tag) for tag in TAGS},
        "claims": rows,
    }


def cmd_mine(args: argparse.Namespace) -> int:
    seed = load_json(DATA / "claims.json")
    proposal = mine(seed["claims"], load_corpus())
    dest = OUT / "pending.json"
    dump_json(dest, proposal)
    print(f"wrote {dest}")
    print("counts:", proposal["counts"])
    print("This is a proposed write. Review it, then: python3 ledger.py approve")
    return 0


def cmd_approve(args: argparse.Namespace) -> int:
    pending_path = OUT / "pending.json"
    if not pending_path.exists():
        print("nothing to approve; run python3 ledger.py mine first", file=sys.stderr)
        return 2
    pending = load_json(pending_path)
    if args.yes is not True:
        print("Pending tags:")
        for row in pending["claims"]:
            print(f"  {row['id']:4}  {row['tag']:9}  {row['text']}")
        print("\nNothing was written. Re-run with --yes after you have read the list.")
        print("That --yes is the human gate.")
        return 0
    ledger = {
        "approved": date.today().isoformat(),
        "approver": args.approver,
        "policy": pending["policy"],
        "counts": pending["counts"],
        "claims": pending["claims"],
    }
    dest = OUT / "ledger.json"
    dump_json(dest, ledger)
    print(f"approved by {args.approver} → {dest}")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    ledger_path = OUT / "ledger.json"
    if not ledger_path.exists():
        print("no approved ledger; mine + approve first", file=sys.stderr)
        return 2
    ledger = load_json(ledger_path)
    lines = [
        f"# Claims ledger — approved {ledger['approved']} by {ledger['approver']}",
        "",
        "Every public sentence has to survive this table. Tags: **verified** · **flagged** · **estimate** · **retire**.",
        "",
        "| ID | Tag | Claim | Why |",
        "|---|---|---|---|",
    ]
    for row in ledger["claims"]:
        why = row["why"].replace("|", "/")
        text = row["text"].replace("|", "/")
        lines.append(f"| {row['id']} | {row['tag']} | {text} | {why} |")
    lines += ["", "## Sources (top hit per claim)", ""]
    for row in ledger["claims"]:
        src = row["sources"][0] if row["sources"] else None
        if not src:
            lines.append(f"- **{row['id']}** — no source")
            continue
        lines.append(
            f"- **{row['id']}** ({src['system']}/{src['id']}): \"{src['quote']}\""
        )
    dest = OUT / "ledger.md"
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {dest}")
    return 0


def evaluate(proposal: dict, gold: dict) -> dict:
    gold_map = {g["id"]: g["tag"] for g in gold["claims"]}
    rows = []
    correct = 0
    for row in proposal["claims"]:
        expected = gold_map[row["id"]]
        ok = row["tag"] == expected
        correct += int(ok)
        rows.append({"id": row["id"], "got": row["tag"], "gold": expected, "ok": ok})
    n = len(rows)
    return {
        "n": n,
        "correct": correct,
        "accuracy": round(correct / n, 3) if n else 0,
        "rows": rows,
        "weak_spot": next((r for r in rows if not r["ok"]), None),
    }


def cmd_eval(args: argparse.Namespace) -> int:
    seed = load_json(DATA / "claims.json")
    proposal = mine(seed["claims"], load_corpus())
    gold = load_json(GOLD)
    result = evaluate(proposal, gold)
    dump_json(OUT / "eval.json", result)
    print(f"accuracy  {result['correct']}/{result['n']}  ({result['accuracy']})")
    if result["weak_spot"]:
        w = result["weak_spot"]
        print(f"weak spot {w['id']}: got {w['got']}, gold {w['gold']}")
    else:
        print("no misses on this gold set — do not treat that as a headline")
    return 0 if result["accuracy"] == 1 else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("mine", help="read the six systems; write out/pending.json (not public yet)")
    ap = sub.add_parser("approve", help="the human gate: copy pending → ledger after you have read it")
    ap.add_argument("--yes", action="store_true", help="I have read the pending tags and accept them")
    ap.add_argument("--approver", default="Aria Chen")
    sub.add_parser("report", help="write out/ledger.md from the approved ledger")
    sub.add_parser("eval", help="score this run against data/gold.json and print the miss")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return {"mine": cmd_mine, "approve": cmd_approve, "report": cmd_report, "eval": cmd_eval}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
