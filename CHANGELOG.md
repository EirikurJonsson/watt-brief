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
- CI: dependency audit, image build attestations (provenance and SBOM), deploy that checks the
  running commit, rolls back on failure and can smoke test the live site.
