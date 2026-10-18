from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date

import requests

BASE_URL = "https://api.massive.com/v2/aggs/grouped/locale/us/market/stocks"


class MassiveAPIError(RuntimeError):
    pass


@dataclass(frozen=True)
class DailyBar:
    ticker: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    vwap: float | None = None

    @property
    def dollar_volume(self) -> float:
        return self.close * self.volume


def fetch_grouped_daily(day: str, api_key: str | None = None, timeout: int = 30) -> dict[str, DailyBar]:
    key = api_key or os.getenv("MASSIVE_API_KEY", "").strip()
    if not key:
        raise MassiveAPIError(
            "MASSIVE_API_KEY is missing. Copy .env.example to .env and add your Massive API key, "
            "or run `python main.py stock demo` to test offline."
        )
    try:
        date.fromisoformat(day)
    except ValueError as exc:
        raise MassiveAPIError(f"Invalid date {day!r}; expected YYYY-MM-DD.") from exc

    try:
        response = requests.get(
            f"{BASE_URL}/{day}",
            params={"adjusted": "true", "include_otc": "false", "apiKey": key},
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise MassiveAPIError(f"Could not reach Massive API: {exc}") from exc

    if response.status_code == 401 or response.status_code == 403:
        raise MassiveAPIError("Massive rejected the API key or plan access (HTTP %s). Check your key and Stocks Basic access." % response.status_code)
    if response.status_code == 429:
        raise MassiveAPIError("Massive rate limit reached. Stocks Basic allows 5 API calls per minute; wait and retry.")
    if response.status_code >= 400:
        body = response.text[:300]
        raise MassiveAPIError(f"Massive API returned HTTP {response.status_code}: {body}")
    try:
        payload = response.json()
    except ValueError as exc:
        raise MassiveAPIError("Massive returned a non-JSON response.") from exc

    raw_results = payload.get("results") or []
    bars: dict[str, DailyBar] = {}
    for item in raw_results:
        try:
            ticker = str(item["T"])
            opn, high, low, close, volume = (float(item[k]) for k in ("o", "h", "l", "c", "v"))
            vwap = float(item["vw"]) if item.get("vw") is not None else None
            if min(opn, high, low, close) <= 0 or volume < 0:
                continue
            bars[ticker] = DailyBar(ticker, opn, high, low, close, volume, vwap)
        except (KeyError, TypeError, ValueError):
            continue
    return bars
