# Status

Treat this as a small production service facing hostile users, not a demo.
Threats and mitigations: [threat-model.md](threat-model.md).

## Plan

1. [x] Repo skeleton, config, ADR 001
2. [ ] Threat model written and reviewed (before any endpoint exists)
3. [x] Structured logging and request IDs from the first line of app code
4. [x] ENTSO-E client built and tested on synthetic fixtures; swap in real recordings once the token works
5. [x] One agent answers one question end to end (on synthetic fixture data)
6. [x] Eval harness: quality and adversarial evals with code graders, live results in docs/eval-results.md; CI runs lint and offline tests (live evals stay manual because they spend money)
7. [x] Input and output guards, layered and measured separately (ADR 002). Open: held-out attack set, non-English questions
7b. [ ] Held-out prompt-injection eval: pull a public prompt-injection dataset (verify its licence and provenance first), run it through the guards without tuning on it, and report the result with the dataset named. Only then claim the guards are tested on attacks we did not write. Also: non-English questions, and legitimate questions with no energy word (input guard false rejections)
8. [x] Planner and critic built and measured (ADR 003): planner on, critic off by default. Open: a harder quality set so the critic can show a benefit if it has one
9. [ ] Metrics and monitoring: latency, error rate, tokens, cost per run, rejected requests
10. [ ] Alerts: spend nearing cap, error spike, abuse pattern
11. [ ] Abuse controls: per-IP rate limit, daily spend cap, kill switch
12. [ ] Deploy on the home server behind Cloudflare Tunnel
13. [ ] Write up cost, latency, attacks seen, and what broke

## What broke

Nothing yet. This file is where it goes when it does.
