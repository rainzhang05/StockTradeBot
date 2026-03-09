from __future__ import annotations

import json
from datetime import UTC, date, datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from stocktradebot.data.models import CorporateActionRecord, DailyBarRecord, ProviderHistoryPayload
from stocktradebot.data.providers.base import ProviderError


class AlphaVantageDailyHistoryProvider:
    name = "alpha_vantage"

    def __init__(self, *, base_url: str, timeout_seconds: float, api_key: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.api_key = api_key

    def fetch_daily_history(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> ProviderHistoryPayload:
        query = urlencode(
            {
                "function": "TIME_SERIES_DAILY_ADJUSTED",
                "outputsize": "full",
                "symbol": symbol,
                "apikey": self.api_key,
            }
        )
        request_url = f"{self.base_url}/query?{query}"
        requested_at = datetime.now(UTC)
        try:
            with urlopen(request_url, timeout=self.timeout_seconds) as response:
                raw_payload = response.read().decode("utf-8")
        except HTTPError as exc:  # pragma: no cover - network dependent
            raise ProviderError(
                f"Alpha Vantage request failed for {symbol}: HTTP {exc.code}"
            ) from exc
        except URLError as exc:  # pragma: no cover - network dependent
            raise ProviderError(f"Alpha Vantage request failed for {symbol}: {exc.reason}") from exc

        payload = json.loads(raw_payload)
        if "Error Message" in payload:
            raise ProviderError(f"Alpha Vantage rejected {symbol}: {payload['Error Message']}")
        if "Note" in payload:
            raise ProviderError(f"Alpha Vantage throttled {symbol}: {payload['Note']}")

        series = payload.get("Time Series (Daily)")
        if not isinstance(series, dict):
            raise ProviderError(f"Alpha Vantage returned no daily series for {symbol}")

        bars: list[DailyBarRecord] = []
        corporate_actions: list[CorporateActionRecord] = []
        for trade_date_text, values in series.items():
            trade_date = datetime.strptime(trade_date_text, "%Y-%m-%d").date()
            if trade_date < start_date or trade_date > end_date:
                continue

            bars.append(
                DailyBarRecord(
                    provider=self.name,
                    symbol=symbol,
                    trade_date=trade_date,
                    open=float(values["1. open"]),
                    high=float(values["2. high"]),
                    low=float(values["3. low"]),
                    close=float(values["4. close"]),
                    volume=int(values["6. volume"]),
                )
            )

            dividend_amount = float(values["7. dividend amount"])
            if dividend_amount != 0:
                corporate_actions.append(
                    CorporateActionRecord(
                        provider=self.name,
                        symbol=symbol,
                        ex_date=trade_date,
                        action_type="dividend",
                        value=dividend_amount,
                    )
                )

            split_coefficient = float(values["8. split coefficient"])
            if split_coefficient != 1:
                corporate_actions.append(
                    CorporateActionRecord(
                        provider=self.name,
                        symbol=symbol,
                        ex_date=trade_date,
                        action_type="split",
                        value=split_coefficient,
                    )
                )

        redacted_url = request_url.replace(self.api_key, "REDACTED")
        return ProviderHistoryPayload(
            provider=self.name,
            symbol=symbol,
            domain="daily_prices",
            requested_at=requested_at,
            request_url=redacted_url,
            payload_format="json",
            raw_payload=raw_payload,
            bars=tuple(sorted(bars, key=lambda bar: bar.trade_date)),
            corporate_actions=tuple(sorted(corporate_actions, key=lambda action: action.ex_date)),
        )
