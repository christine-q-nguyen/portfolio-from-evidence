"""Job search in a box: turn the approved claims ledger into tailored résumés, a role-fit map, and a weekly digest.

Everything here reads out/ledger.json, the file `python3 ledger.py approve --yes` writes, so nothing a person
has not approved reaches a résumé. No dependencies. The digest runs offline on data/postings.json; --live reads
the public job boards listed in data/targets.json instead.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
import sys
import urllib.request
from datetime import date

import ledger

DATA, OUT = ledger.DATA, ledger.OUT
USABLE = ("verified", "estimate")


def load_ledger() -> dict | None:
    path = OUT / "ledger.json"
    return ledger.load_json(path) if path.exists() else None


def has(text: str, keywords: list[str]) -> list[str]:
    low = text.lower()
    return [k for k in keywords if re.search(r"(?<![a-z])" + re.escape(k.lower()) + r"(?![a-z])", low)]


def phrase(row: dict) -> str:
    """The sentence a résumé may use: verified claims as written, estimates in their softened form."""
    if row["tag"] == "estimate" and row.get("rewrite"):
        return row["rewrite"].split(" — ")[0].rstrip(".,") + "."
    return row["text"]


def proof(requirement: dict, rows: list[dict]) -> tuple[list[str], list[str]]:
    """Claims that back a requirement: usable (verified or estimate), and flagged ones still waiting on a source."""
    usable, waiting = [], []
    for row in rows:
        if has(row["text"], requirement["keywords"]):
            if row["tag"] in USABLE:
                usable.append(row["id"])
            elif row["tag"] == "flagged":
                waiting.append(row["id"])
    return usable, waiting


# ---------- résumés ----------

def build_resume(led: dict, persona: dict, role: dict) -> tuple[str, list[str], list[dict]]:
    rows = led["claims"]
    keep = [r for r in rows if r["tag"] in USABLE]
    left_out = [r for r in rows if r["tag"] not in USABLE]
    weight = lambda r: sum(len(has(r["text"], q["keywords"])) for q in role["requirements"])
    recent = sorted((r for r in keep if r.get("used_as") != "earlier-career"), key=lambda r: (-weight(r), r["id"]))
    earlier = [r for r in keep if r.get("used_as") == "earlier-career"]
    lines = [f"# {persona['name']}", "", f"**{role['title']}**", "", role["summary"], "", "## Selected results", ""]
    lines += [f"- {phrase(r)}" for r in recent]
    if earlier:
        lines += ["", "## Earlier", ""] + [f"- {phrase(r)}" for r in earlier]
    used = [r["id"] for r in recent + earlier]
    return "\n".join(lines) + "\n", used, left_out


def cmd_resume(args: argparse.Namespace) -> int:
    led = load_ledger()
    if not led:
        print("no approved ledger: run python3 ledger.py mine, read it, then approve --yes", file=sys.stderr)
        return 2
    persona = ledger.load_json(DATA / "claims.json")["persona"]
    roles = ledger.load_json(DATA / "roles.json")["roles"]
    chosen = [r for r in roles if args.role in (None, r["id"])]
    if not chosen:
        print(f"no role {args.role!r} in data/roles.json", file=sys.stderr)
        return 2
    for role in chosen:
        text, used, left_out = build_resume(led, persona, role)
        dest = OUT / f"resume-{role['id']}.md"
        dest.write_text(text, encoding="utf-8")
        print(f"wrote {dest}: {len(used)} claims ({', '.join(used)})")
    print("left out of every version: " + ", ".join(f"{r['id']} ({r['tag']}: {r['why']})" for r in left_out))
    return 0


# ---------- role fit ----------

def fit(led: dict, roles_doc: dict) -> dict:
    rows = led["claims"]
    out = {}
    for role in roles_doc["roles"]:
        proven, verify, gaps = [], [], []
        for req in role["requirements"]:
            usable, waiting = proof(req, rows)
            if usable:
                proven.append({"need": req["need"], "claims": usable})
            elif waiting:
                verify.append({"need": req["need"], "claims": waiting})
            else:
                gaps.append({"need": req["need"]})
        out[role["id"]] = {"title": role["title"], "score": round(100 * len(proven) / len(role["requirements"])),
                           "proven": proven, "verify": verify, "gaps": gaps}
    return out


def cmd_fit(args: argparse.Namespace) -> int:
    led = load_ledger()
    if not led:
        print("no approved ledger: run python3 ledger.py mine, read it, then approve --yes", file=sys.stderr)
        return 2
    result = fit(led, ledger.load_json(DATA / "roles.json"))
    best = max(result.values(), key=lambda r: r["score"])
    lines = [f"# Role fit, from the ledger approved {led['approved']}", "",
             "Proof comes only from verified or estimate claims. A flagged claim is what to verify next.", "",
             f"Strongest fit today: **{best['title']}** ({best['score']}% of its requirements proven).", ""]
    for r in sorted(result.values(), key=lambda r: -r["score"]):
        lines += [f"## {r['title']}: {r['score']}% proven", ""]
        lines += [f"- **proven** {p['need']} ({', '.join(p['claims'])})" for p in r["proven"]]
        lines += [f"- **verify next** {v['need']}: only flagged claims ({', '.join(v['claims'])}) back it. Find a second source."
                  for v in r["verify"]]
        lines += [f"- **gap** {g['need']}: nothing in your records yet." for g in r["gaps"]]
        lines.append("")
    ledger.dump_json(OUT / "fit.json", result)
    (OUT / "fit.md").write_text("\n".join(lines), encoding="utf-8")
    for r in sorted(result.values(), key=lambda r: -r["score"]):
        print(f"{r['score']:3}%  {r['title']}")
    print(f"wrote {OUT / 'fit.md'}")
    return 0


# ---------- weekly digest ----------

def comp_top(comp: str) -> int | None:
    vals = []
    for num, k in re.findall(r"\$\s?([\d,.]+)\s*([kK])?", comp or ""):
        v = float(num.replace(",", ""))
        vals.append(int(v * 1000) if k else int(v))
    return max(vals) if vals else None


def score_posting(p: dict, roles_doc: dict, rows: list[dict]) -> dict:
    title, text, wants = p["title"].lower(), f"{p['title']} {p.get('text', '')}", roles_doc["wants"]
    best = None
    for role in roles_doc["roles"]:
        family = any(t in title for t in role["match_titles"])
        asked = [q for q in role["requirements"] if has(text, q["keywords"])]
        backed = [(q, *proof(q, rows)) for q in asked]
        proven = [q["need"] for q, u, _ in backed if u]
        verify = sorted({c for q, u, w in backed if not u for c in w})
        gaps = [q["need"] for q, u, w in backed if not u and not w]
        raw = (3 if family else 0) + 4 * len(proven) / max(len(asked), 3)
        cand = {"role": role["title"] if family else None, "raw": raw, "proven": proven, "verify": verify, "gaps": gaps}
        if best is None or raw > best["raw"]:
            best = cand
    where_ok = any(w in p.get("location", "").lower() for w in wants["locations"])
    top = comp_top(p.get("comp", ""))
    pay_ok = top is None or top >= wants["min_base"]
    senior = any(re.search(r"(?<![a-z])" + lv + r"(?![a-z])", title) for lv in wants["levels"])
    raw = best["raw"] + (1.5 if where_ok else 0) + (1 if pay_ok else 0) + (0.5 if senior else 0)
    below = [why for ok, why in ((where_ok, "location"), (pay_ok, "pay below your floor")) if not ok]
    return dict(best, id=p["id"], company=p["company"], title=p["title"], location=p.get("location", ""),
                comp=p.get("comp", ""), url=p.get("url", ""), raw=round(raw, 2), fit=max(0, min(10, round(raw))), below=below)


UA = "portfolio-from-evidence weekly digest"


def _get(url: str, timeout: int = 20):
    """urllib first. Python builds without the system certificate store (or behind a company proxy) fail TLS
    verification, so fall back to curl, which uses the operating system's store."""
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as exc:
        if "CERTIFICATE_VERIFY_FAILED" not in str(exc) and "SSL" not in str(exc):
            raise
        res = subprocess.run(["curl", "-sSL", "--fail", "--max-time", str(timeout), "-A", UA, url],
                             capture_output=True, text=True, check=False)
        if res.returncode != 0 or not res.stdout:
            raise RuntimeError(f"curl fallback failed ({res.returncode}): {res.stderr.strip()[:80]}") from exc
        return json.loads(res.stdout)


def _plain(markup: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(markup or ""))).strip()


def live_postings(targets: list[dict]) -> tuple[list[dict], list[str]]:
    """Read public job boards (Greenhouse, Ashby, Lever). One failing board never stops the digest."""
    posts, errors = [], []
    for t in targets:
        try:
            if t["ats"] == "greenhouse":
                for j in _get(f"https://boards-api.greenhouse.io/v1/boards/{t['token']}/jobs?content=true")["jobs"]:
                    posts.append({"id": f"gh:{t['token']}:{j['id']}", "company": t["company"], "title": j["title"],
                                  "location": (j.get("location") or {}).get("name", ""), "comp": "",
                                  "url": j.get("absolute_url", ""), "text": _plain(j.get("content", ""))})
            elif t["ats"] == "ashby":
                data = _get(f"https://api.ashbyhq.com/posting-api/job-board/{t['token']}?includeCompensation=true")
                for j in data.get("jobs", []):
                    comp = ((j.get("compensation") or {}).get("compensationTierSummary")) or ""
                    posts.append({"id": f"ashby:{t['token']}:{j['id']}", "company": t["company"], "title": j["title"],
                                  "location": j.get("location", "") + (" · remote" if j.get("isRemote") else ""),
                                  "comp": comp, "url": j.get("jobUrl", ""), "text": j.get("descriptionPlain", "")})
            elif t["ats"] == "lever":
                for j in _get(f"https://api.lever.co/v0/postings/{t['token']}?mode=json"):
                    pay = j.get("salaryRange") or {}
                    comp = f"${pay['min']:,} – ${pay['max']:,}" if pay.get("max") else ""
                    posts.append({"id": f"lever:{t['token']}:{j['id']}", "company": t["company"], "title": j["text"],
                                  "location": (j.get("categories") or {}).get("location", ""), "comp": comp,
                                  "url": j.get("hostedUrl", ""), "text": j.get("descriptionPlain", "")})
            else:
                errors.append(f"{t['company']}: unknown board type {t['ats']!r}")
        except Exception as e:  # network, auth, or a changed API: say so in the digest and keep going
            errors.append(f"{t['company']} ({t['ats']}): {e}")
    return posts, errors


def cmd_digest(args: argparse.Namespace) -> int:
    led = load_ledger()
    if not led:
        print("no approved ledger: run python3 ledger.py mine, read it, then approve --yes", file=sys.stderr)
        return 2
    roles_doc = ledger.load_json(DATA / "roles.json")
    if args.live:
        tpath = DATA / "targets.json"
        if not tpath.exists():
            print("copy data/targets.example.json to data/targets.json and list your companies first", file=sys.stderr)
            return 2
        posts, errors, source = *live_postings(ledger.load_json(tpath)["targets"]), "public job boards"
    else:
        posts, errors, source = ledger.load_json(DATA / "postings.json")["postings"], [], "data/postings.json (demo)"
    seen_path = OUT / "seen.json"
    seen = set(ledger.load_json(seen_path)) if seen_path.exists() else set()
    new = [p for p in posts if args.all or p["id"] not in seen]
    if not new and not errors:
        print("no new roles since the last digest (use --all to rank everything again)")
        return 0
    scored = sorted((score_posting(p, roles_doc, led["claims"]) for p in new), key=lambda s: (-s["fit"], -s["raw"], s["id"]))
    ranked, below = [s for s in scored if not s["below"]], [s for s in scored if s["below"]]
    today = date.today().isoformat()
    lines = [f"# Weekly digest, {today}", "",
             f"Source: {source} · new since last run: {len(new)} · already seen: {len(posts) - len(new)}", "",
             "Fit is 0–10: the role family, how much of what the posting asks for your approved claims prove, and your "
             "location and pay floor.", "", "## New roles, ranked by fit", "",
             "| Fit | Company | Role | Location | Pay | What you can prove | Verify or close first |", "|---|---|---|---|---|---|---|"]
    cell = lambda v: str(v).replace("|", "/").strip()
    for s in ranked[:args.top]:
        todo = "; ".join(([f"verify {', '.join(s['verify'])}"] if s["verify"] else []) + [f"gap: {g.lower()}" for g in s["gaps"]][:2])
        proven = "; ".join(s["proven"]) or "nothing yet"
        if not s["role"] and not s["proven"]:
            proven, todo = "outside your role families", "add the family to data/roles.json if you want it"
        lines.append(f"| {s['fit']} | {cell(s['company'])} | [{cell(s['title'])}]({s['url']}) | {cell(s['location'])} "
                     f"| {cell(s['comp'] or 'not posted')} | {proven} | {todo or 'ready'} |")
    if len(ranked) > args.top:
        lines += ["", f"…and {len(ranked) - args.top} more in out/digest.json (raise --top to list them)."]
    if below:
        lines += ["", "## Below your bar", ""]
        lines += [f"- {s['company']}, {s['title']} ({s['location']}, {s['comp'] or 'pay not posted'}): {', '.join(s['below'])}"
                  for s in below[:10]]
        if len(below) > 10:
            lines.append(f"- …and {len(below) - 10} more")
    if errors:
        lines += ["", "## Boards that didn't answer", ""] + [f"- {e}" for e in errors]
    dest = OUT / f"digest-{today}.md"
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ledger.dump_json(OUT / "digest.json", {"date": today, "ranked": ranked, "below": below, "errors": errors, "new": len(new)})
    ledger.dump_json(seen_path, sorted(seen | {p["id"] for p in posts}))
    for s in ranked[:5]:
        print(f"{s['fit']:2}  {s['company']}: {s['title']}")
    print(f"wrote {dest} ({len(ranked)} ranked, {len(below)} below your bar)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("resume", help="one résumé per role family in data/roles.json, from approved claims only")
    r.add_argument("--role", help="build just this role id")
    sub.add_parser("fit", help="how much of each role's requirements your approved claims prove, and what to verify next")
    d = sub.add_parser("digest", help="this week's new roles, ranked by fit (offline demo unless --live)")
    d.add_argument("--live", action="store_true", help="read the public job boards in data/targets.json")
    d.add_argument("--all", action="store_true", help="include roles already seen in an earlier digest")
    d.add_argument("--top", type=int, default=20, help="how many ranked roles to list (default 20)")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return {"resume": cmd_resume, "fit": cmd_fit, "digest": cmd_digest}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
