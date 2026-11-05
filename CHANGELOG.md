# Changelog

Notable changes, newest first. Versions are git tags; the running commit is shown by `/healthz`.

## Unreleased

- Prices for Denmark (DK1, DK2) with a fixed EUR to DKK conversion; DK1 is the default zone.
- Each delivery day is fetched from ENTSO-E once, stored in the history table and served from
  cache; a background loop fetches tomorrow's prices as soon as they are published.
- Page and briefs in English, Danish, German and French.
- Data-path metrics (`wb_entsoe_fetches_total`, `wb_price_cache_total`, `wb_stale_zones`,
  `wb_history_rows`, `wb_warm_failures_total`) and a `version` field on `/healthz`.
- Versioned history schema (migrations), nightly-safe database backups
  (`python -m watt_brief.backup`), property-based tests for the parser and guards.
- Phone layout: the answer and chart come first, the choices below; the browser check now runs in
  CI. Nightly live evals with pass thresholds (`--gate`).
- Graceful shutdown verified by test (in-flight request survives SIGTERM); compose fragment
  gets `stop_grace_period: 30s`.
- Briefs and the chart no longer recommend a window that has already started: part-way through
  today, only windows from the current slot onward are considered (`windows_from_utc` in the facts).
- Prices shown to two decimals everywhere; all times are UTC only (no browser-local or CET times
  on the page, in the table or in briefs).
- Questions that limit the hours of use ("I can charge between 08:00 and 16:00"): the hours are
  read as local time for the zone's country, the cheapest window is found inside them, and the
  brief states the hours in UTC. Fixes such questions being refused as "unsafe".
- CI: dependency audit, image build attestations (provenance and SBOM), deploy that checks the
  running commit, rolls back on failure and can smoke test the live site.
