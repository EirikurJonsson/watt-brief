# Status

Treat this as a small production service facing hostile users, not a demo.
Threats and mitigations: [threat-model.md](threat-model.md).

## Plan

1. [x] Repo skeleton, config, ADR 001
2. [ ] Threat model written and reviewed (before any endpoint exists)
3. [x] Structured logging and request IDs from the first line of app code
4. [x] ENTSO-E client built and tested on synthetic fixtures; swap in real recordings once the token works
5. [x] One agent answers one question end to end (on synthetic fixture data)
6. [ ] Eval harness: quality evals and adversarial evals (injection, off-topic, abuse), run in CI
7. [ ] Input guards: length limit, topic check, structured output only
8. [ ] Add planner and critic, measure whether they help, record in an ADR
9. [ ] Metrics and monitoring: latency, error rate, tokens, cost per run, rejected requests
10. [ ] Alerts: spend nearing cap, error spike, abuse pattern
11. [ ] Abuse controls: per-IP rate limit, daily spend cap, kill switch
12. [ ] Deploy on the home server behind Cloudflare Tunnel
13. [ ] Write up cost, latency, attacks seen, and what broke

## What broke

Nothing yet. This file is where it goes when it does.
