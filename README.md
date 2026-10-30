# portfolio-from-evidence

[![tests](https://github.com/christine-q-nguyen/portfolio-from-evidence/actions/workflows/tests.yml/badge.svg)](https://github.com/christine-q-nguyen/portfolio-from-evidence/actions/workflows/tests.yml) ![license: MIT](https://img.shields.io/badge/license-MIT-blue) ![python: 3.10+](https://img.shields.io/badge/python-3.10%2B-blue) ![dependencies: none](https://img.shields.io/badge/dependencies-none-brightgreen)

A job search in a box, built from your own records instead of your memory. It's the method behind [my portfolio](https://christinenguyen.me), rebuilt with made-up data so you can run it. The story is a [case study on the site](https://christinenguyen.me/work/case-portfolio-method.html).

Most people write their portfolio and résumé from memory, then spend hours hunting for evidence, capturing visuals, and sanitizing work. Even then, the result may not fit the role or the market they're applying to. This starts from the records:

1. **Write down** every claim you want to make.
2. **Check** each one against your systems of record (tickets, chat, calendar, Git, documents, meetings): verified, flagged, estimate, or retire.
3. **Approve** the tags yourself. Nothing goes public until you do.
4. **Tailor** a résumé for each kind of role, from approved claims only.
5. **Check your fit:** what each role asks for, what you can prove, and what to verify next.
6. **Keep up:** a weekly digest of new roles at the companies you care about, ranked by fit.

No dependencies. Python 3.10+. MIT licensed. Every name and number in the demo is made up.

The sister project is [transcript-to-requirements](https://github.com/christine-q-nguyen/transcript-to-requirements): one discovery meeting in, requirements your developers can build from out.

## Quick start

```bash
python3 ledger.py mine       # check the claims against six systems; write out/pending.json
python3 ledger.py approve    # print the proposed tags; write nothing
python3 ledger.py approve --yes --approver "Your Name"
python3 ledger.py report     # out/ledger.md: every claim, its tag, and the quote behind it

python3 jobsearch.py resume  # out/resume-<role>.md: one résumé per role family
python3 jobsearch.py fit     # out/fit.md: what each role asks for that you can prove
python3 jobsearch.py digest  # out/digest-<date>.md: new roles, ranked by fit

python3 ledger.py eval       # score the checking step against data/gold.json
python3 -m unittest -q
```

`approve` without `--yes` is the point. Changing a claim's public status is a write, so a person decides. Reading never waits, and `jobsearch.py` only reads the approved ledger, so nothing you haven't approved reaches a résumé.

## The demo

A fictional enablement lead, Aria Chen, is changing roles. Her draft résumé makes seven claims. Checking them against Harbor Labs (also fictional) does this:

| ID | Draft claim | Tag | Why |
|---|---|---|---|
| C01 | Cut the time from AI idea to first prototype from three months to about ten days. | verified | Ticket + meeting transcript agree. |
| C02 | Grew the AI request backlog 180% since I joined. | **retire** | 180 is the backlog size, not growth. |
| C03 | Sorted 142 AI requests; 61 were data-quality fixes, not AI work. | verified | Ticket + readout agree. |
| C04 | Routing accuracy reached 97% in production. | estimate | Notebook result. Say "in our testing." |
| C05 | Trained 40 people in one week. | flagged | The number only lives in chat. The calendar says not to quote it. |
| C06 | Clinic check-in wait 14 → 5 minutes; satisfaction 3.9 → 4.6. | verified | Closeout document. |
| C07 | Ran a standing monthly AI review with the leadership team. | gold: verified | Calendar is enough for a person. The checker flags it. |

C02 is the headline that dies before a recruiter sees it. C07 is the published miss: a true fact that lives in only one system, which the heuristic won't promote on its own.

### What the job search finds

Aria assumed she wanted AI enablement lead roles. Her approved claims say something else:

```
$ python3 jobsearch.py fit
 80%  AI Adoption Product Manager
 75%  Service Design Lead
 40%  AI Enablement Lead
```

The enablement lead role is held back by exactly the two claims the ledger flagged: C05 (training) and C07 (the leadership review). So `fit` tells her what to do next: find a second source for those two, and start measuring adoption, which nothing in her records shows yet.

The résumés follow the same rule. All three versions use the four claims that survived (C01, C03, C04 as "in our testing", C06), ordered by what each role asks for, and leave out C02, C05, and C07 with the reason printed.

The digest ranks this week's postings the same way (eight made-up postings in `data/postings.json`):

```
$ python3 jobsearch.py digest
 9  Woodgrove Bank: AI Adoption Product Manager
 9  Tailspin Toys: Service Design Lead
 8  Adventure Works: Director, AI Transformation
 7  Contoso: Head of AI Enablement
 6  Fabrikam: AI Enablement Lead, Sales
```

Each row says what she can prove, what to verify before applying (Contoso: verify C05 and C07), and which roles fall below her bar on location or pay. Run it again and it only shows what's new.

## Eval (this commit)

```
accuracy  6/7  (0.857)
weak spot C07: got flagged, gold verified
```

CI runs the demo and the tests on every push, and fails if this result changes.

Don't turn 86% into a headline. The useful sentence is: **single-source facts still need a person.**

## Use it on your own search

| File | Put in it |
|---|---|
| `data/claims.json` | Your draft claims, one per résumé line you want to make |
| `data/systems/*.json` | Exports from your tools (or fill the same shape from MCP servers or a browser) |
| `data/roles.json` | The role families you're weighing, what their postings ask for, and your location and pay floor |
| `data/targets.json` | The companies to watch (copy `data/targets.example.json`; it's git-ignored) |

Re-run `mine`. Don't run `approve --yes` until you've read every retire and every estimate.

`python3 jobsearch.py digest --live` reads the public job boards in `data/targets.json` (Greenhouse, Ashby, and Lever). A board that doesn't answer is listed in the digest instead of stopping it. To get it every Monday at 8 am, add a cron line (or a launchd job on a Mac):

```
0 8 * * 1  cd /path/to/portfolio-from-evidence && python3 jobsearch.py digest --live
```

A read-only MCP server is in `mcp_server.py` if you want an agent to inspect the ledger. It can't approve.

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

- It contains no employer or client data, code, prompts, or names. Aria, Jordan, Harbor Labs, and the companies in the demo postings are made up, and so is every number.
- It is not a hosted app, and it won't apply to jobs for you.
- It will not write to your résumé file, LinkedIn, or GitHub.
- It will not tag a claim "verified" because a language model sounds sure.
- The fit score is a heuristic to sort your reading list, not a verdict. Read the posting.

## License

MIT. See `LICENSE`.
