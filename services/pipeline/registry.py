from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json
import sqlite3

from services.pipeline.artifacts import write_json_artifact
from services.pipeline.features import FEATURE_NAMES


ARTIFACTS_DIR = Path(__file__).resolve().parent.parent.parent / "artifacts" / "metadata"


@dataclass(frozen=True)
class ModelRegistration:
    model_version: str
    model_family: str
    dataset_version: str
    timeframe: str
    horizons: list[str]
    symbols: list[str]
    metrics: dict[str, float]
    training_run_id: str
    training_window_start: str
    training_window_end: str
    feature_schema_version: str
    logic_version: str
    hyperparameters: dict[str, float | int | str]
    model_payload: dict
    registered_at: str



def build_model_registration(
    model_family: str,
    dataset_version: str,
    timeframe: str,
    horizon: str,
    symbols: list[str],
    metrics: dict[str, float],
    training_run_id: str,
    training_window_start: str,
    training_window_end: str,
    feature_schema_version: str,
    logic_version: str,
    hyperparameters: dict[str, float | int | str],
    model_payload: dict,
) -> ModelRegistration:
    digest = sha256(
        json.dumps(
            {
                "model_family": model_family,
                "dataset_version": dataset_version,
                "timeframe": timeframe,
                "horizon": horizon,
                "symbols": symbols,
                "feature_schema_version": feature_schema_version,
                "logic_version": logic_version,
                "hyperparameters": hyperparameters,
                "model_payload": model_payload,
            },
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()[:12]
    return ModelRegistration(
        model_version=f"{model_family}-{digest}",
        model_family=model_family,
        dataset_version=dataset_version,
        timeframe=timeframe,
        horizons=[horizon],
        symbols=symbols,
        metrics=metrics,
        training_run_id=training_run_id,
        training_window_start=training_window_start,
        training_window_end=training_window_end,
        feature_schema_version=feature_schema_version,
        logic_version=logic_version,
        hyperparameters=hyperparameters,
        model_payload=model_payload,
        registered_at=datetime.now(timezone.utc).isoformat(),
    )



def register_model(connection: sqlite3.Connection, registration: ModelRegistration) -> bool:
    cursor = connection.execute(
        """
        INSERT OR IGNORE INTO model_versions(
            model_version,
            model_family,
            dataset_version,
            horizons_json,
            symbol_scope_json,
            metrics_json,
            registered_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            registration.model_version,
            registration.model_family,
            registration.dataset_version,
            json.dumps(registration.horizons),
            json.dumps(registration.symbols),
            json.dumps(
                {
                    **registration.metrics,
                    "timeframe": registration.timeframe,
                    "training_run_id": registration.training_run_id,
                    "training_window_start": registration.training_window_start,
                    "training_window_end": registration.training_window_end,
                    "feature_schema_version": registration.feature_schema_version,
                    "feature_names": FEATURE_NAMES,
                    "logic_version": registration.logic_version,
                    "hyperparameters": registration.hyperparameters,
                    "model_payload": registration.model_payload,
                },
                sort_keys=True,
            ),
            registration.registered_at,
        ),
    )
    return cursor.rowcount == 1



def write_model_artifact(registration: ModelRegistration) -> None:
    artifact_path = ARTIFACTS_DIR / f"{registration.model_version}.json"
    write_json_artifact(
        artifact_path,
        {
            "model_version": registration.model_version,
            "model_family": registration.model_family,
            "dataset_version": registration.dataset_version,
            "timeframe": registration.timeframe,
            "horizons": registration.horizons,
            "symbols": registration.symbols,
            "metrics": registration.metrics,
            "training_run_id": registration.training_run_id,
            "training_window_start": registration.training_window_start,
            "training_window_end": registration.training_window_end,
            "feature_schema_version": registration.feature_schema_version,
            "feature_names": FEATURE_NAMES,
            "logic_version": registration.logic_version,
            "hyperparameters": registration.hyperparameters,
            "model_payload": registration.model_payload,
        },
    )



def load_model_artifact(model_version: str) -> dict:
    artifact_path = ARTIFACTS_DIR / f"{model_version}.json"
    return json.loads(artifact_path.read_text(encoding="utf-8"))
