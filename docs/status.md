# Status

Treat this as a small production service facing hostile users, not a demo.
Threats and mitigations: [threat-model.md](threat-model.md).

## Plan

1. [x] Repo skeleton, config, ADR 001
2. [x] Threat model written, and reviewed against the built system on 1 Nov. Still open there: things outside the repository (provider spend limit, Cloudflare rule, branch protection)
3. [x] Structured logging and request IDs from the first line of app code
4. [x] ENTSO-E client built and tested; live on 2 Nov. Real recordings added as fixtures (`live_*`). Live check found two parser bugs (several TimeSeries per response; intraday series in ES), both fixed. Open: confirm what ENTSO-E's "sequence 2" is; we use sequence 1, which matches ES's coupled price
5. [x] One agent answers one question end to end (on synthetic fixture data)
6. [x] Eval harness: quality and adversarial evals with code graders, live results in docs/eval-results.md; CI runs lint and offline tests (live evals stay manual because they spend money)
7. [x] Input and output guards, layered and measured separately (ADR 002). Open: held-out attack set, non-English questions
7b. [x] Held-out prompt-injection eval, done 1 Nov on two public datasets (docs/injection-eval.md); non-English questions and keywordless questions fixed. Still open: attacks in French, Spanish and Dutch, and a semantic measure of hijacking. Original task: pull a public prompt-injection dataset (verify its licence and provenance first), run it through the guards without tuning on it, and report the result with the dataset named. Only then claim the guards are tested on attacks we did not write. Also: non-English questions, and legitimate questions with no energy word (input guard false rejections) Attacks in FR/ES/NL/DE: 80/80 guarded, 78/80 model alone (docs/eval-results.md).
8. [x] Planner and critic built and measured (ADR 003): planner on, critic off by default. Open: a harder quality set so the critic can show a benefit if it has one
9. [x] Service API with Prometheus metrics (docs/operations.md)
10. [x] Alerts: spend, error spike, abuse pattern, bans, kill switch. Logs only for now (decision: no webhook yet; ALERT_WEBHOOK_URL is ready when wanted)
11. [x] Abuse controls: rate limit, temporary bans, persisted daily spend cap, kill switch, concurrency and body limits
12. [x] UI: plain HTML page with strict CSP, redesigned around the price chart (ADR 004, docs/design.md), checked in a real browser (scripts/ui_check.mjs)
13. [ ] Deploy on the home server behind Cloudflare Tunnel. Repo side done and checked as far as possible without Docker (Dockerfile, compose fragment, CI/CD, smoke script, runbook in docs/deploy.md). Needs from Eirikur: GitHub secrets, server env file and compose merge over SSH, Cloudflare hostname route. First real image build happens in CI.
14. [ ] Write up cost, latency, attacks seen, and what broke Outline with sources for every claim: [writeup-outline.md](writeup-outline.md). Real-data sections are pending.
15. [~] Alerts to ntfy (1 Nov). Code, tests and docs done: `ALERT_WEBHOOK_FORMAT=ntfy`. Not live until Eirikur picks a topic and sets the two env vars on the server; the external uptime check and a real end-to-end trigger are still open.
    - `alerts.py` posts JSON `{"text": ...}` to `ALERT_WEBHOOK_URL`. ntfy wants a plain-text body with
      optional `Title`, `Priority` and `Tags` headers, so add an `ALERT_WEBHOOK_FORMAT=ntfy` option
      (critical alerts at high priority, warnings at default).
    - On ntfy.sh the topic name is the only secret, so use a long random topic and treat the URL
      like a key, or self-host ntfy on the home server and put it behind auth.
    - Also add an external uptime check (the in-process alerts cannot fire if the service is down).
    - Test: unit test for the request shape, then trigger a real alert with the kill switch.
15b. [x] Price history (2 Nov): SQLite `prices` table, written on every fetch, backs the stale fallback after a restart, backfill script, "compared with the day before" on the chart. Data freshness in `/healthz` plus a `stale_data` alert. Daily live contract check in CI (needs the `ENTSOE_API_TOKEN` repository secret). See docs/operations.md. Open: no feature reads history beyond the day-before figure; the brief itself does not yet use it (the grounding guards would need to learn the new numbers)
16. [ ] Product decision: should briefs be written in the language of the question? Today the
    question can be in five languages and the brief is always English.

## What broke

A lot, and it is written up honestly in [what-broke.md](what-broke.md).
