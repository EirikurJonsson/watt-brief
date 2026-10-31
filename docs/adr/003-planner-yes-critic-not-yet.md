# ADR 003: Ship the planner, leave the critic off

Status: accepted
Date: 2026-10-31

## Context

The first version was one agent. We added two more and wanted to know whether each earns its
cost, not assume it. Both are switchable (`use_planner`, `use_critic`) and were compared on
the same cases, 5 repeats each, all guards on. Details: `docs/eval-results.md`.

## Decision

- **Planner: on by default.** It turns the question into an enum-checked plan (zone, window
  hours, intent). It scored 45/45 on its own eval and did not hurt quality or safety. It costs
  about 40% more per request. What it buys is not a higher score on the existing suite: it is
  a capability. Without it the zone is hard-coded, and a question about France or Sweden gets
  the wrong answer or a silent swap. A separate `UNSUPPORTED` answer lets us say "I don't
  cover that" instead of answering for the wrong country.
- **Critic: off by default.** It roughly doubled cost and added about a second of latency. It
  asked for a revision on about 1 request in 7. It improved nothing we can measure: quality was
  already 25/25 without it, so there was no headroom to show a gain. The deterministic
  grounding guard already catches the failure the critic is meant to catch (invented numbers).

| Config | Quality | Adversarial | Cost vs analyst only | Median latency |
|---|---|---|---|---|
| Analyst only | 25/25 | 75/75 | 1.0x | 3.4 s |
| + planner | 25/25 | 75/75 | 1.4x | 4.2 s |
| + critic | 25/25 | 73/75 | 2.0x | 4.3 s |
| + both | 25/25 | 75/75 | 2.2x | 4.5 s |

## Options considered

- **Keep the critic on "for safety".** Rejected: safety comes from the deterministic guards
  (ADR 002), and a second model adds a model-to-model injection path. Its issues are
  sanitised before reuse, but the path still exists.
- **Drop the critic from the code.** Rejected: the evidence is that this test set cannot show
  a benefit, not that there is none. The code stays behind a flag.

## Consequences

- The critic is advisory and fails open: if it errors, the draft stands.
- Every request through the planner makes two model calls, so the spend cap in step 11 must
  count all calls, not requests.

## What would change this

Turn the critic on if we find failures the guards cannot see, mainly answers that are fully
grounded but answer the wrong question. The current quality set is easy for the model, so
build a harder one first (ambiguous questions, conflicting constraints, multi-part requests),
then re-run the comparison. If the critic still shows no gain there, remove it.
