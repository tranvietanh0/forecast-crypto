# forecast-crypto

## Phase 1 foundation

Python-first foundation for an event-driven crypto forecasting platform.

### Module boundaries
- `contracts/` — shared event and config contracts used by every future service.
- `services/ingestion/` — market data capture and normalization boundary.
- `services/pipeline/` — offline feature generation and dataset/version ownership.
- `services/inference/` — scheduled forecast generation boundary.
- `services/api/` — forecast storage and read API boundary.
- `services/telegram/` — scheduled notification delivery boundary.
- `services/monitoring/` — realized outcome, drift, and quality monitoring boundary.
- `apps/dashboard/` — dashboard application boundary.
- `infra/migrations/` — storage schema and append-only event log evolution.
- `config/` — SSOT defaults for coin universe, horizons, provider endpoints, cadences, and retention.

### Shared event contracts
- `MarketEvent`
- `FeatureSetBuilt`
- `ModelRegistered`
- `ForecastGenerated`
- `NotificationSnapshot`

Every consumer should read the same forecast payload for `trend` and `target_price` so dashboard and Telegram stay consistent.

### Local validation
- Copy `.env.example` to `.env` and set `DATABASE_URL`.
- Run migrations: `python tools/migrate.py up sqlite:///:memory:`
- Run tests: `python tests/run-tests.py`
