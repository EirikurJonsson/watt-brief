# Load test

`uv run python scripts/loadtest.py` starts a fake model server (`scripts/fake_llm.py`, 2.5 s per
call, two calls per brief) and the real service, then sends bursts at rising concurrency. It
spends nothing. Rate limits and the spend cap are raised so they do not get in the way. The
concurrency limit is the default, 4.

Run on a developer laptop, 1 November 2026. Each worker sends 3 requests back to back.

| Workers | Requests | OK | Busy (503) | p50 s | p95 s | OK per second | CPU ms per request | Memory MB |
|---|---|---|---|---|---|---|---|---|
| 1 | 3 | 3 | 0 | 5.0 | 5.1 | 0.20 | 33 | 63 |
| 2 | 6 | 6 | 0 | 5.0 | 5.0 | 0.40 | 23 | 63 |
| 4 | 12 | 12 | 0 | 5.1 | 5.1 | 0.79 | 23 | 64 |
| 8 | 24 | 12 | 12 | 5.1 | 5.1 | 0.79 | 12 | 64 |
| 16 | 48 | 12 | 36 | 5.1 | 5.1 | 0.79 | 7 | 64 |
| 32 | 96 | 12 | 84 | 5.0 | 5.2 | 0.79 | 4 | 65 |

Memory at start was 62 MB.

## What it shows

- **The service adds almost nothing.** A brief takes 5.0 to 5.1 seconds when the two fake model
  calls take 5.0. Its own overhead is about 0.1 s.
- **Throughput scales to the concurrency limit, then stops.** It rises with workers up to 4
  (0.79 per second), then stays flat. That is the limit working as designed.
- **Overload is rejected at once, not queued.** Past 4 in flight, extra requests get an
  immediate 503 "busy". Latency for the requests that are served does not degrade.
- **Memory is flat** at about 64 MB through 32 concurrent clients, and CPU use per request is in
  the tens of milliseconds. The service is limited by the model's latency, not its own work.

## What it does not show

- **Not the model provider.** The fake server answers on time, every time. Real latency varies,
  and real providers rate limit. Retries for that are tested with unit tests, not here.
- **Not the home server.** This ran on a laptop. The server's CPU is different. Numbers for it
  need the same script run there.
- **Not network effects.** No Cloudflare, no tunnel, no slow clients.

## Decisions this supports

- **A concurrency limit of 4 is fine for now.** At roughly 5 seconds per brief it allows about
  0.8 briefs per second, far more than the daily spend cap lets through: at about $0.0001 to
  $0.0002 per brief in the evals, a $1 cap is several thousand briefs a day.
- **Rejecting instead of queueing is a choice.** It keeps an attack from piling up waiting
  requests, and the page tells the visitor to try again. A short queue of a second or two would
  be kinder to real users in a burst. Not built, because under attack the simple behaviour is
  safer. Revisit if "busy" shows up in the metrics for real visitors (`wb_requests_total{outcome="busy"}`).
