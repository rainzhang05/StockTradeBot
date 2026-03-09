from __future__ import annotations

import csv
from datetime import UTC, date, datetime
from io import StringIO
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from stocktradebot.data.models import DailyBarRecord, ProviderHistoryPayload
from stocktradebot.data.providers.base import ProviderError


def resolve_stooq_symbol(symbol: str) -> str:
    normalized = symbol.strip().lower().replace(".", "-")
    return f"{normalized}.us"


class StooqDailyHistoryProvider:
    name = "stooq"

    def __init__(self, *, base_url: str, timeout_seconds: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def fetch_daily_history(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> ProviderHistoryPayload:
        request_url = f"{self.base_url}/q/d/l/?s={resolve_stooq_symbol(symbol)}&i=d"
        requested_at = datetime.now(UTC)
        try:
            with urlopen(request_url, timeout=self.timeout_seconds) as response:
                raw_payload = response.read().decode("utf-8")
        except HTTPError as exc:  # pragma: no cover - network dependent
            raise ProviderError(f"Stooq request failed for {symbol}: HTTP {exc.code}") from exc
        except URLError as exc:  # pragma: no cover - network dependent
            raise ProviderError(f"Stooq request failed for {symbol}: {exc.reason}") from exc

        bars: list[DailyBarRecord] = []
        reader = csv.DictReader(StringIO(raw_payload))
        for row in reader:
            if not row.get("Date"):
                continue
            trade_date = datetime.strptime(row["Date"], "%Y-%m-%d").date()
            if trade_date < start_date or trade_date > end_date:
                continue
            bars.append(
                DailyBarRecord(
                    provider=self.name,
                    symbol=symbol,
                    trade_date=trade_date,
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                    volume=int(float(row["Volume"] or 0)),
                )
            )

        return ProviderHistoryPayload(
            provider=self.name,
            symbol=symbol,
            domain="daily_prices",
            requested_at=requested_at,
            request_url=request_url,
            payload_format="csv",
            raw_payload=raw_payload,
            bars=tuple(sorted(bars, key=lambda bar: bar.trade_date)),
        )
