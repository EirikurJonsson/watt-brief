# Operations

Single instance, one process. Bind to localhost and expose only through the Cloudflare Tunnel.
Deployment steps: [deploy.md](deploy.md).

```
uv run python -m watt_brief.serve     # 127.0.0.1:8000
```

## Controls

| Control | Where | Default |
|---|---|---|
| Kill switch | create the file `KILL_SWITCH` (setting `KILL_SWITCH_FILE`) to stop all model calls, delete it to resume. In the container: `touch watt-brief-data/KILL_SWITCH` next to the compose file | off |
| Daily spend cap | `DAILY_SPEND_CAP_USD`, counted in a SQLite file so a restart cannot reset it | $1.00 |
| Rate limit | `RATE_LIMIT_PER_MINUTE`, `RATE_LIMIT_PER_DAY`, per client | 6 / 100 |
| Temporary ban | 10 guard rejections in 10 minutes bans a client for an hour | on |
| Concurrency | `MAX_CONCURRENT_REQUESTS`, extra requests get 503 | 4 |
| Body size | 4 KB, enforced while streaming | on |

Order of checks, cheapest first: kill switch, ban, rate limit, spend cap, body, concurrency,
then the model. Rejected traffic costs nothing.

## Things to know

- **Cost overshoot.** The cap is checked before a request and cost is added after each model
  call, so in-flight requests can overshoot it by at most `MAX_CONCURRENT_REQUESTS` requests.
  At current prices that is a fraction of a cent.
- **Unknown cost.** If the provider reports no cost, each call counts as
  `FALLBACK_COST_PER_CALL_USD`, so the cap is never blind.
- **Client identity.** Behind the tunnel every connection comes from localhost, so set
  `TRUST_CF_CONNECTING_IP=true` to use Cloudflare's header. Never set it if the port is
  reachable any other way: the header is spoofable.
- **Single instance.** Rate limits and bans live in memory and reset on restart. Spend does not.
- **Synthetic data.** With `FACTS_SOURCE=fixture` every response says `"data_source": "synthetic"`.

## Metrics

`GET /metrics` returns 404 unless `METRICS_TOKEN` is set, then needs `Authorization: Bearer <token>`.
Useful series: `wb_requests_total{outcome}`, `wb_guard_rejections_total{stage,reason}`,
`wb_request_seconds`, `wb_llm_tokens_total`, `wb_llm_cost_usd_total`, `wb_spend_today_usd`,
`wb_spend_cap_usd`, `wb_banned_clients`, `wb_kill_switch`.

## Alerts

Evaluated after every request. Each fires at most once per 30 minutes.

| Alert | Severity | When |
|---|---|---|
| `spend_high` | warning | spend at 80% of the daily cap |
| `spend_cap` | critical | cap reached |
| `error_spike` | critical | more than 20% of the last 50 requests failed (needs 20 requests) |
| `abuse_pattern` | warning | more than 50% of the last 50 requests rejected or rate limited |
| `bans_active` | warning | any client is banned |
| `kill_switch` | critical | kill switch on |

Alerts always go to the log (WARNING or ERROR). Set `ALERT_WEBHOOK_URL` to also send them to a
webhook. The URL is never logged, because it can hold a token.

`ALERT_WEBHOOK_FORMAT` picks the body:
- `json` (default): `{"text": "[watt-brief critical] ..."}`, which Slack-style hooks accept.
- `ntfy`: the message as plain text, with `Title`, `Priority` (`high` for critical, `default` for
  warnings) and `Tags` headers. Use `https://ntfy.sh/<topic>` or your own ntfy server.

On ntfy.sh anyone who knows the topic name can read it and post to it. Use a long random topic
(for example `openssl rand -hex 16`), keep it only in the server env file, and treat it like a key.
Alerts contain counts and percentages, never question text. In-process alerts cannot fire when the
service is down, so also point an external uptime check at `/healthz`.

## Price data and history

- **Fetch once.** Day-ahead prices for a delivery day are final once published, so each zone and
  day is fetched once, then served from memory and from the history table. Nothing expires by age,
  and a restart needs no ENTSO-E calls. That is about one request per zone per day, plus the
  checks for tomorrow below.
- **Tomorrow's prices** exist from about 12:45 Brussels time. They are not requested before
  12:30; after that the service asks every 10 minutes until they appear, then keeps them. Until
  then today's prices are served. If they are still missing at 15:00, `/healthz` reports
  `"status": "degraded"` with the zones in `stale_zones`, and a `stale_data` warning goes to the
  alert webhook. The container healthcheck still passes.
- **Warm-up.** A background task fetches every zone at start-up and every 5 minutes after, so a
  user's request finds the prices already in the cache. `prices_through` in `/healthz` is the last
  delivery date held for every zone. If ENTSO-E is down for today's prices, requests get "not
  available" and are retried at most once a minute.
- **Default zone** is DK1 (`DEFAULT_ZONE` overrides it; the synthetic demo day is German, so it
  uses DE_LU). It applies when neither the page nor the question names a country.
- **Languages.** The page and the written brief come in English, Danish, German and French. The
  choice defaults to the browser's language and is remembered in that browser only. Server errors
  carry a stable `code`; the page shows its own translation of it, and API users get the English
  `error` text.
- **History.** Every fetch is upserted into `data/history.sqlite` (table `prices`: zone, UTC slot
  start, EUR/MWh, resolution, fetch time), only when `FACTS_SOURCE=entsoe`. It survives restarts,
  answers when ENTSO-E is down after a restart, and gives the "compared with the day before" line.
  Back it up by copying the file (`sqlite3 history.sqlite ".backup copy.sqlite"` is safe while the
  service runs). It holds about 96 rows per zone per day.
- **Backfill** past days (idempotent): `docker compose exec watt_brief python -m watt_brief.backfill --days 30`
- **Contract check.** `.github/workflows/contract-check.yml` runs `scripts/contract_check.py`
  daily against the live API: one clean day per zone, no duplicate timestamps, plausible prices. It
  needs the repository secret `ENTSOE_API_TOKEN` and skips itself without it.
- **Fixtures.** `tests/fixtures/live_*` are recorded responses; re-record with
  `scripts/record_fixture.py`.

## Model provider failures

Transient failures (timeouts, connection errors, HTTP 408, 429 and 5xx) are retried up to
`LLM_MAX_RETRIES` times (default 2) with exponential backoff, inside `LLM_RETRY_BUDGET_SECONDS`
(default 40) per model call. A 429 `Retry-After` is honoured up to 5 seconds. Bad keys and bad
requests (other 4xx) are never retried. Retries are counted in `wb_llm_retries_total{reason}`.
A failed attempt costs nothing, because cost is counted from the response of the attempt that
succeeded. A request makes at least two model calls (planner and analyst), so its worst case is
longer than one call's budget; the page gives up after 60 seconds.
