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
9. [x] Service API with Prometheus metrics (docs/operations.md)
10. [x] Alerts: spend, error spike, abuse pattern, bans, kill switch. Logs only for now (decision: no webhook yet; ALERT_WEBHOOK_URL is ready when wanted)
11. [x] Abuse controls: rate limit, temporary bans, persisted daily spend cap, kill switch, concurrency and body limits
12. [x] UI: one plain HTML page with strict CSP, checked in a real browser (ADR 004, scripts/ui_check.mjs)
13. [ ] Deploy on the home server behind Cloudflare Tunnel. Repo side done and checked as far as possible without Docker (Dockerfile, compose fragment, CI/CD, smoke script, runbook in docs/deploy.md). Needs from Eirikur: GitHub secrets, server env file and compose merge over SSH, Cloudflare hostname route. First real image build happens in CI.
14. [ ] Write up cost, latency, attacks seen, and what broke

## What broke

Nothing yet. This file is where it goes when it does.
