# Write-up outline (status.md item 14)

Not the article. A skeleton in which every claim points at the file that backs it, so the finished
piece cannot drift from the evidence. A section marked **pending** needs real market data or real
traffic and must not be written from the synthetic day.

Voice: short, plain, apolitical. Failures get as much space as successes. No figure appears
without a source in the third column.

## Thesis

A model on the public internet is a system with a budget, an attack surface and an owner who wants
to sleep. The model is the smallest part of making that safe. Most of the work is code around it,
and every layer can be measured.

## Sections

| # | Section | Point | Evidence | State |
|---|---|---|---|---|
| 1 | What it is | European day-ahead power prices, one question, one grounded answer. A demo with a cap on what it can cost | `README.md`, live page | Ready |
| 2 | The shape | Plan with a small model call, compute with code, write with the model, check with code. The model never does arithmetic the page shows | `src/watt_brief/pipeline.py`, `analysis.py`; models behind one OpenAI-compatible interface: `docs/adr/001` | Ready |
| 3 | Guards before model | Rejected requests cost nothing. Output must be grounded in the facts | `docs/adr/002`, `docs/eval-results.md` | Ready |
| 4 | What each layer buys | Same cases, layers switched off one at a time | `docs/eval-results.md` (table "What each layer contributes") | Ready |
| 5 | Attacks nobody here wrote | 172 held-out prompts from two public datasets. Raw: most stopped at the input guard. Wrapped in a real question: the model alone broke the contract 4 times in 336 answers, the guarded service 0 | `docs/injection-eval.md` | Ready, with its stated limits |
| 6 | Other languages | 21 of 24 ordinary non-English questions were rejected at first; fixed; attacks in those languages measured | `docs/eval-results.md`, `docs/what-broke.md` | Ready once the French, Spanish and Dutch attack run is recorded |
| 7 | A critic that did not help | A second model checking the first doubled the cost and measured no benefit, so it is off | `docs/adr/003` | Ready |
| 8 | What broke | The honest list, in the order it was found | `docs/what-broke.md` | Ready, keep adding |
| 9 | Load and cost behaviour | Overload fails fast, memory stays flat, the spend cap holds | `docs/load-test.md` (fake model) | Ready, **but** cost per real brief is pending |
| 10 | Cost per brief | Measured from `wb_llm_cost_usd_total` and the eval result files | Eval result JSON files; metrics after real traffic | **Pending** |
| 11 | Real data | Replace the synthetic day: record real fixtures, re-run every suite on them, report what changed | `docs/status.md` item 5 and onward | **Pending** (ENTSO-E token) |
| 12 | What the public did | Visits, questions rejected, alerts fired, attacks seen | Metrics and Umami, counts only | **Pending** (needs traffic) |
| 13 | What I would not claim | Not a security guarantee, not adaptive-attacker tested, English and German datasets only, synthetic prices until section 11 | `docs/threat-model.md`, `docs/injection-eval.md` | Ready |

## Rules for the final piece

- Every number is copied from the file named above, with the date of the run.
- Political text from the test datasets never appears. Counts only.
- If a later run disagrees with a figure here, the later run wins and the change is told, as in
  `docs/eval-results.md`.
- The live page says "synthetic" until section 11 is done, and so does the write-up.

## Open before publishing

- Section 10 and 11 need the token and a week of traffic.
- Decide where it is published, and whether the repository link goes on `cpa-intel.tech`.
- The "Past the Demo" series ties in at sections 2, 3 and 7.
