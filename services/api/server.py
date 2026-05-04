from __future__ import annotations

from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse
import json

from services.api.handlers import ApiError, get_forecast_batch_detail, get_forecast_history, get_latest_forecasts
from tools.migrate import connect


class ForecastApiHandler(BaseHTTPRequestHandler):
    database_url = "sqlite:///./forecast_crypto.db"

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
            self._write_json(500, {"error": "internal server error"})

    def _route(self, path: str, query: dict[str, list[str]]) -> dict:
        with connect(self.database_url) as connection:
            if path == "/forecasts/latest":
                timeframe = _required(query, "timeframe")
                horizon = _required(query, "horizon")
                watchlist = query.get("watchlist", [""])[0]
                symbols = [item for item in watchlist.split(",") if item] if watchlist else None
                return get_latest_forecasts(connection, timeframe, horizon, symbols)
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
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)



def _required(query: dict[str, list[str]], key: str) -> str:
    values = query.get(key)
    if not values or not values[0]:
        raise ValueError(f"Missing required query parameter: {key}")
    return values[0]



def run_api_server(database_url: str, host: str = "127.0.0.1", port: int = 8000) -> HTTPServer:
    handler = type("ConfiguredForecastApiHandler", (ForecastApiHandler,), {"database_url": database_url})
    server = HTTPServer((host, port), handler)
    return server


if __name__ == "__main__":
    server = run_api_server("sqlite:///./forecast_crypto.db")
    server.serve_forever()
