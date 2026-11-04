# Fixtures

`day_ahead_*.xml` and `acknowledgement_no_data.xml` are **synthetic**. They follow ENTSO-E's
documented response format, but the prices are made up.

`live_*.xml` are **recorded from the live API** (document type A44, delivery day
2026-11-02, Brussels time). They hold what the synthetic files do not: several `TimeSeries` for one
interval (two sequences of the daily auction for DE_LU; the daily series plus three intraday
auctions for ES), 15-minute resolution, and compressed (A03) curves. The API token is not part of
a response. Re-record with `scripts/record_fixture.py` if the format changes.
