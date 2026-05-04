from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
import json
import logging
import os

from services.api.handlers import ApiError, get_forecast_batch_detail, get_forecast_history, get_latest_forecasts
from services.ingestion.ingest import DEFAULT_TIMEFRAME, sync_live_forecasts
from tools.migrate import apply_all, connect


logger = logging.getLogger(__name__)
DEFAULT_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./forecast_crypto.db")


class ForecastApiHandler(BaseHTTPRequestHandler):
    database_url = DEFAULT_DATABASE_URL

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        try:
            payload = self._route(parsed.path, query)
            self._write_json(200, payload)
        except ApiError as error:
            self._write_json(404, {"error": str(error)})
        except ValueError as error:
            self._write_json(400, {"error": str(error)})
        except Exception:
            logger.exception("Unhandled API error for path %s", self.path)
            self._write_json(500, {"error": "internal server error"})

    def _route(self, path: str, query: dict[str, list[str]]) -> dict:
        with connect(self.database_url) as connection:
            if path == "/forecasts/latest":
                timeframe = _required(query, "timeframe")
                horizon = _required(query, "horizon")
                watchlist = query.get("watchlist", [""])[0]
                symbols = [item for item in watchlist.split(",") if item] if watchlist else None
                try:
                    return get_latest_forecasts(connection, timeframe, horizon, symbols)
                except ApiError as error:
                    if str(error) != "No ready forecast batch found":
                        raise
                    sync_live_forecasts(
                        connection,
                        self.database_url,
                        timeframe=timeframe,
                        horizons=[horizon],
                        requested_symbols=symbols,
                    )
                    return get_latest_forecasts(connection, timeframe, horizon, symbols)
            if path == "/forecasts/refresh":
                timeframe = query.get("timeframe", [DEFAULT_TIMEFRAME])[0]
                horizon = _required(query, "horizon")
                watchlist = query.get("watchlist", [""])[0]
                symbols = [item for item in watchlist.split(",") if item] if watchlist else None
                sync_result = sync_live_forecasts(
                    connection,
                    self.database_url,
                    timeframe=timeframe,
                    horizons=[horizon],
                    requested_symbols=symbols,
                )
                latest_payload = get_latest_forecasts(connection, timeframe, horizon, symbols)
                return {
                    **latest_payload,
                    "sync": sync_result,
                }
            if path == "/forecasts/history":
                symbol = _required(query, "symbol")
                timeframe = _required(query, "timeframe")
                horizon = _required(query, "horizon")
                limit = int(query.get("limit", ["20"])[0])
                return get_forecast_history(connection, symbol, timeframe, horizon, limit)
            if path.startswith("/forecast-batches/"):
                batch_id = path.removeprefix("/forecast-batches/")
                return get_forecast_batch_detail(connection, batch_id)
        raise ApiError(f"Unknown route: {path}")

    def _write_json(self, status_code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)



def _required(query: dict[str, list[str]], key: str) -> str:
    values = query.get(key)
    if not values or not values[0]:
        raise ValueError(f"Missing required query parameter: {key}")
    return values[0]



def run_api_server(database_url: str, host: str = "127.0.0.1", port: int = 8000) -> ThreadingHTTPServer:
    handler = type("ConfiguredForecastApiHandler", (ForecastApiHandler,), {"database_url": database_url})
    server = ThreadingHTTPServer((host, port), handler)
    return server


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    apply_all(DEFAULT_DATABASE_URL, "up")
    with connect(DEFAULT_DATABASE_URL) as connection:
        sync_live_forecasts(connection, DEFAULT_DATABASE_URL)
    server = run_api_server(DEFAULT_DATABASE_URL)
    server.serve_forever()
