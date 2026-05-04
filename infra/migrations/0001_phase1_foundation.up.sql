CREATE TABLE IF NOT EXISTS raw_market_events (
    event_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    provider TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    open_time TEXT NOT NULL,
    close_time TEXT NOT NULL,
    open_price REAL NOT NULL,
    high_price REAL NOT NULL,
    low_price REAL NOT NULL,
    close_price REAL NOT NULL,
    volume REAL NOT NULL,
    captured_at TEXT NOT NULL,
    payload_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_raw_market_events_symbol_close_time
    ON raw_market_events (symbol, close_time);

CREATE TABLE IF NOT EXISTS dataset_versions (
    dataset_version TEXT PRIMARY KEY,
    symbol_scope_json TEXT NOT NULL,
    horizon_scope_json TEXT NOT NULL,
    feature_names_json TEXT NOT NULL,
    source_start_time TEXT NOT NULL,
    source_end_time TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS model_versions (
    model_version TEXT PRIMARY KEY,
    model_family TEXT NOT NULL,
    dataset_version TEXT NOT NULL,
    horizons_json TEXT NOT NULL,
    symbol_scope_json TEXT NOT NULL,
    metrics_json TEXT NOT NULL,
    registered_at TEXT NOT NULL,
    FOREIGN KEY (dataset_version) REFERENCES dataset_versions(dataset_version)
);

CREATE TABLE IF NOT EXISTS forecast_batches (
    forecast_batch_id TEXT PRIMARY KEY,
    model_version TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    horizon TEXT NOT NULL,
    forecast_time TEXT NOT NULL,
    coin_universe_json TEXT NOT NULL,
    batch_status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (model_version) REFERENCES model_versions(model_version)
);

CREATE TABLE IF NOT EXISTS forecasts (
    forecast_id TEXT PRIMARY KEY,
    forecast_batch_id TEXT NOT NULL,
    model_version TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    horizon TEXT NOT NULL,
    forecast_time TEXT NOT NULL,
    target_time TEXT NOT NULL,
    trend TEXT NOT NULL,
    target_price REAL NOT NULL,
    confidence REAL NOT NULL,
    generated_at TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    FOREIGN KEY (forecast_batch_id) REFERENCES forecast_batches(forecast_batch_id),
    FOREIGN KEY (model_version) REFERENCES model_versions(model_version)
);

CREATE INDEX IF NOT EXISTS idx_forecasts_batch_symbol
    ON forecasts (forecast_batch_id, symbol);

CREATE TABLE IF NOT EXISTS notification_runs (
    notification_run_id TEXT PRIMARY KEY,
    forecast_batch_id TEXT NOT NULL,
    delivery_channel TEXT NOT NULL,
    scheduled_for TEXT NOT NULL,
    message_preview TEXT NOT NULL,
    sent_at TEXT,
    status TEXT NOT NULL,
    FOREIGN KEY (forecast_batch_id) REFERENCES forecast_batches(forecast_batch_id)
);

CREATE TABLE IF NOT EXISTS realized_outcomes (
    outcome_id TEXT PRIMARY KEY,
    forecast_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    horizon TEXT NOT NULL,
    target_time TEXT NOT NULL,
    realized_price REAL NOT NULL,
    realized_trend TEXT NOT NULL,
    measured_at TEXT NOT NULL,
    FOREIGN KEY (forecast_id) REFERENCES forecasts(forecast_id)
);

CREATE TABLE IF NOT EXISTS event_log (
    log_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    published_at TEXT,
    status TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_event_log_status_created_at
    ON event_log (status, created_at);
