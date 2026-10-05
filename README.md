# portfolio-from-evidence

[![tests](https://github.com/christine-q-nguyen/portfolio-from-evidence/actions/workflows/tests.yml/badge.svg)](https://github.com/christine-q-nguyen/portfolio-from-evidence/actions/workflows/tests.yml) ![license: MIT](https://img.shields.io/badge/license-MIT-blue) ![python: 3.10+](https://img.shields.io/badge/python-3.10%2B-blue) ![dependencies: none](https://img.shields.io/badge/dependencies-none-brightgreen)

The method I used to build [my portfolio](https://christinenguyen.me), rebuilt so you can run it. The story behind it is a [case study on the site](https://christinenguyen.me/work/case-portfolio-method.html).

Confidential systems make a weak argument. This repo is the public version: six fictional systems, a claims ledger, a human gate on every write, and an eval that publishes its miss.

No dependencies. Python 3.10+. MIT licensed. All names and numbers are synthetic.

## What it is

Most people write a resume from memory, then go looking for proof. I did the reverse.

1. Write down every claim you want to make.
2. Mine the systems of record (tickets, chat, calendar, git, documents, meetings).
3. Tag each claim **verified**, **flagged**, **estimate**, or **retire**.
4. A person approves the tags before anything is public.
5. Publish the eval, including the miss.

The sister project is intake: a recorded call in, structured requirements out. This one is scattered evidence in, a story you can defend out.

## Quick start

```bash
python3 ledger.py mine       # read the six systems; write out/pending.json
python3 ledger.py approve    # print the proposed tags; write nothing
python3 ledger.py approve --yes --approver "Your Name"
python3 ledger.py report     # write out/ledger.md
python3 ledger.py eval       # score this run against data/gold.json
python3 -m unittest -q
```

`approve` without `--yes` is the point. Changing a claim's public status is a write. Reads never wait.

## The demo corpus

A fictional enablement lead, Aria Chen, is changing roles. Her draft resume makes seven claims. Mining against Harbor Labs (also fictional) does this:

| ID | Draft claim | Tag | Why |
|---|---|---|---|
| C01 | Cut the time from AI idea to first prototype from three months to about ten days. | verified | Ticket + meeting transcript agree. |
| C02 | Grew the AI request backlog 180% since I joined. | **retire** | 180 is the backlog size, not growth. |
| C03 | Sorted 142 AI requests; 61 were data-quality fixes, not AI work. | verified | Ticket + readout agree. |
| C04 | Routing accuracy reached 97% in production. | estimate | Notebook result. Say "in our testing." |
| C05 | Trained 40 people in one week. | flagged | The number only lives in chat. The calendar says not to quote it. |
| C06 | Clinic check-in wait 14 → 5 minutes; satisfaction 3.9 → 4.6. | verified | Closeout document. |
| C07 | Ran a standing monthly AI review with the leadership team. | gold: verified | Calendar is enough for a person. The miner flags it. |

C02 is the headline that dies. C07 is the published miss: a true single-system fact that the heuristic will not promote on its own. That is the load-aware version of a human in the loop. Approve the borderline writes; let the obvious reads run.

## Eval (this commit)

```
accuracy  6/7  (0.857)
weak spot C07: got flagged, gold verified
```

CI runs the demo on every push and fails if this result changes.

Do not turn 86% into a headline. The useful sentence is: **single-source facts still need a person.**

## Use it on your own evidence

Replace `data/claims.json` with your draft claims. Replace `data/systems/*.json` with exports from your tools (or keep the shape and fill it from MCP servers / a browser). Re-run `mine`. Do not run `approve --yes` until you have read every retire and every estimate.

A read-only MCP server is in `mcp_server.py` if you want an agent to inspect the ledger. It cannot approve.

```json
{
  "mcpServers": {
    "portfolio-from-evidence": {
      "command": "python3",
      "args": ["/absolute/path/to/portfolio-from-evidence/mcp_server.py"]
    }
  }
}
```

## What this is not

- It contains no employer or client data, code, prompts, or names. Aria, Jordan, and Harbor Labs are made up, and so is every number.
- It is not a hosted app.
- It will not write to your resume, LinkedIn, or GitHub.
- It will not tag a claim "verified" because a language model sounds sure.

## License

MIT. See `LICENSE`.
