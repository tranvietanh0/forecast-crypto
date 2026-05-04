from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json
import sqlite3

from contracts.timeframe import horizon_to_steps
from services.ingestion.storage import load_market_events
from services.pipeline.artifacts import write_json_artifact
from services.pipeline.features import FEATURE_NAMES, FEATURE_SCHEMA_VERSION, FeatureRow, build_feature_row


ARTIFACTS_DIR = Path(__file__).resolve().parent.parent.parent / "artifacts" / "metadata"
MIN_HISTORY_EVENTS = 7


@dataclass(frozen=True)
class DatasetBundle:
    dataset_version: str
    feature_schema_version: str
    timeframe: str
    horizon: str
    symbols: list[str]
    rows: list[FeatureRow]
    created_at: str


class DatasetError(RuntimeError):
    pass



def _source_start_time(rows: list[FeatureRow]) -> str:
    return min(row.source_start_time for row in rows)



def _source_end_time(rows: list[FeatureRow]) -> str:
    return max(row.target_time for row in rows)



def build_dataset_bundle(
    connection: sqlite3.Connection,
    symbols: list[str],
    timeframe: str,
    horizon: str,
) -> DatasetBundle:
    horizon_steps = horizon_to_steps(timeframe, horizon)
    dataset_rows: list[FeatureRow] = []
    for symbol in symbols:
        events = load_market_events(connection, symbol, timeframe)
        if len(events) < MIN_HISTORY_EVENTS + horizon_steps:
            continue
        for current_index in range(MIN_HISTORY_EVENTS - 1, len(events) - horizon_steps):
            dataset_rows.append(build_feature_row(events, current_index, horizon_steps, horizon))

    if not dataset_rows:
        raise DatasetError("No dataset rows could be built from the available raw events")

    dataset_rows = sorted(
        dataset_rows,
        key=lambda row: (row.symbol, row.feature_timestamp, row.target_time),
    )
    actual_symbols = sorted({row.symbol for row in dataset_rows})
    digest_source = {
        "symbols": actual_symbols,
        "timeframe": timeframe,
        "horizon": horizon,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "rows": [
            {
                "symbol": row.symbol,
                "feature_timestamp": row.feature_timestamp,
                "forecast_time": row.forecast_time,
                "source_start_time": row.source_start_time,
                "target_time": row.target_time,
                "current_price": row.current_price,
                "feature_values": row.feature_values,
                "source_event_ids": row.source_event_ids,
                "target_price": row.target_price,
                "future_return": row.future_return,
                "trend_label": row.trend_label,
            }
            for row in dataset_rows
        ],
    }
    dataset_version = "dataset-" + sha256(
        json.dumps(digest_source, sort_keys=True).encode("utf-8")
    ).hexdigest()[:12]
    created_at = datetime.now(timezone.utc).isoformat()
    return DatasetBundle(
        dataset_version=dataset_version,
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        timeframe=timeframe,
        horizon=horizon,
        symbols=actual_symbols,
        rows=dataset_rows,
        created_at=created_at,
    )



def register_dataset(
    connection: sqlite3.Connection,
    dataset_bundle: DatasetBundle,
) -> bool:
    source_start_time = _source_start_time(dataset_bundle.rows)
    source_end_time = _source_end_time(dataset_bundle.rows)
    cursor = connection.execute(
        """
        INSERT OR IGNORE INTO dataset_versions(
            dataset_version,
            symbol_scope_json,
            horizon_scope_json,
            feature_names_json,
            source_start_time,
            source_end_time,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            dataset_bundle.dataset_version,
            json.dumps(dataset_bundle.symbols),
            json.dumps([dataset_bundle.horizon]),
            json.dumps(FEATURE_NAMES),
            source_start_time,
            source_end_time,
            dataset_bundle.created_at,
        ),
    )
    return cursor.rowcount == 1



def write_dataset_artifact(dataset_bundle: DatasetBundle) -> None:
    source_start_time = _source_start_time(dataset_bundle.rows)
    source_end_time = _source_end_time(dataset_bundle.rows)
    artifact_path = ARTIFACTS_DIR / f"{dataset_bundle.dataset_version}.json"
    write_json_artifact(
        artifact_path,
        {
            "dataset_version": dataset_bundle.dataset_version,
            "feature_schema_version": dataset_bundle.feature_schema_version,
            "timeframe": dataset_bundle.timeframe,
            "horizon": dataset_bundle.horizon,
            "symbols": dataset_bundle.symbols,
            "feature_names": FEATURE_NAMES,
            "row_count": len(dataset_bundle.rows),
            "source_start_time": source_start_time,
            "source_end_time": source_end_time,
        },
    )
