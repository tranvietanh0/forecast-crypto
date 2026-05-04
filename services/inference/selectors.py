from __future__ import annotations

import json
import sqlite3

from services.pipeline.datasets import build_dataset_bundle, load_dataset_artifact
from services.pipeline.registry import load_model_artifact


class ModelSelectionError(RuntimeError):
    pass



def load_latest_model_versions(
    connection: sqlite3.Connection,
    timeframe: str,
    horizon: str,
    symbols: list[str],
) -> dict[str, str]:
    rows = connection.execute(
        "SELECT model_version, model_family, dataset_version, horizons_json, symbol_scope_json, metrics_json, registered_at FROM model_versions ORDER BY registered_at DESC"
    ).fetchall()
    requested_symbols = set(symbols)
    candidate_groups: dict[tuple[int, str], dict] = {}

    for model_version, model_family, dataset_version, horizons_json, symbol_scope_json, metrics_json, registered_at in rows:
        horizons = json.loads(horizons_json)
        metrics = json.loads(metrics_json)
        model_symbols = set(json.loads(symbol_scope_json))
        model_timeframe = _resolve_model_timeframe(
            connection,
            model_version,
            dataset_version,
            sorted(model_symbols),
            horizon,
            metrics,
        )
        if model_timeframe != timeframe:
            continue
        if horizon not in horizons:
            continue

        if model_symbols == requested_symbols:
            match_rank = 0
        elif requested_symbols.issubset(model_symbols):
            match_rank = 1
        else:
            continue

        lineage_key = metrics.get("training_run_id", dataset_version)
        group_key = (match_rank, lineage_key)
        group = candidate_groups.setdefault(
            group_key,
            {
                "registered_at": registered_at,
                "models": {},
            },
        )
        if registered_at > group["registered_at"]:
            group["registered_at"] = registered_at
        group["models"].setdefault(model_family, model_version)

    complete_groups = [
        (group_key, group)
        for group_key, group in candidate_groups.items()
        if "nearest-centroid-classifier" in group["models"]
        and "linear-price-regressor" in group["models"]
    ]
    if not complete_groups:
        raise ModelSelectionError(
            f"Missing registered model pair for timeframe {timeframe}, horizon {horizon}, symbols {sorted(symbols)}"
        )

    complete_groups.sort(key=lambda item: item[0][0])
    best_match_rank = complete_groups[0][0][0]
    best_group = max(
        [group for group_key, group in complete_groups if group_key[0] == best_match_rank],
        key=lambda group: group["registered_at"],
    )
    return {
        "nearest-centroid-classifier": best_group["models"]["nearest-centroid-classifier"],
        "linear-price-regressor": best_group["models"]["linear-price-regressor"],
    }



def _resolve_model_timeframe(
    connection: sqlite3.Connection,
    model_version: str,
    dataset_version: str,
    symbols: list[str],
    horizon: str,
    metrics: dict,
) -> str | None:
    model_timeframe = metrics.get("timeframe")
    if model_timeframe is not None:
        return model_timeframe
    try:
        artifact = load_model_artifact(model_version)
        model_timeframe = artifact.get("timeframe")
        if model_timeframe is not None:
            return model_timeframe
    except FileNotFoundError:
        pass
    try:
        dataset_artifact = load_dataset_artifact(dataset_version)
        model_timeframe = dataset_artifact.get("timeframe")
        if model_timeframe is not None:
            return model_timeframe
    except FileNotFoundError:
        pass
    return _infer_timeframe_from_dataset(connection, dataset_version, symbols, horizon)



def _infer_timeframe_from_dataset(
    connection: sqlite3.Connection,
    dataset_version: str,
    symbols: list[str],
    horizon: str,
) -> str | None:
    for candidate_timeframe in ("1h", "4h", "1d"):
        try:
            dataset_bundle = build_dataset_bundle(connection, symbols, candidate_timeframe, horizon)
        except Exception:
            continue
        if dataset_bundle.dataset_version == dataset_version:
            return candidate_timeframe
    return None
