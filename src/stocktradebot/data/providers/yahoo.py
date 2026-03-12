from __future__ import annotations

import json
from datetime import UTC, date, datetime, time, timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from stocktradebot.data.models import (
    CorporateActionRecord,
    DailyBarRecord,
    ProviderHistoryPayload,
)
from stocktradebot.data.providers.base import ProviderError

_REQUEST_USER_AGENT = "Mozilla/5.0"


def resolve_yahoo_symbol(symbol: str) -> str:
    return symbol.strip().upper().replace(".", "-")


def _split_ratio(value: dict[str, object]) -> float | None:
    numerator = value.get("numerator")
    denominator = value.get("denominator")
    if (
        isinstance(numerator, int | float)
        and isinstance(denominator, int | float)
        and denominator != 0
    ):
        return float(numerator) / float(denominator)
    ratio = value.get("splitRatio")
    if isinstance(ratio, str) and ":" in ratio:
        left, right = ratio.split(":", maxsplit=1)
        if float(right) == 0:
            return None
        return float(left) / float(right)
    return None


class YahooDailyHistoryProvider:
    name = "yahoo"

    def __init__(self, *, base_url: str, timeout_seconds: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def fetch_daily_history(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> ProviderHistoryPayload:
        yahoo_symbol = resolve_yahoo_symbol(symbol)
        period1 = int(datetime.combine(start_date, time.min, tzinfo=UTC).timestamp())
        period2 = int(
            datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=UTC).timestamp()
        )
        query = urlencode(
            {
                "interval": "1d",
                "includeAdjustedClose": "true",
                "events": "div,splits",
                "period1": str(period1),
                "period2": str(period2),
            }
        )
        request_url = f"{self.base_url}/v8/finance/chart/{yahoo_symbol}?{query}"
        requested_at = datetime.now(UTC)
        request = Request(request_url, headers={"User-Agent": _REQUEST_USER_AGENT})
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                raw_payload = response.read().decode("utf-8")
        except HTTPError as exc:  # pragma: no cover - network dependent
            raise ProviderError(f"Yahoo request failed for {symbol}: HTTP {exc.code}") from exc
        except URLError as exc:  # pragma: no cover - network dependent
            raise ProviderError(f"Yahoo request failed for {symbol}: {exc.reason}") from exc

        payload = json.loads(raw_payload)
        chart = payload.get("chart")
        if not isinstance(chart, dict):
            raise ProviderError(f"Yahoo returned an unexpected payload for {symbol}")
        error = chart.get("error")
        if error:
            description = (
                error.get("description") if isinstance(error, dict) else "unknown chart error"
            )
            raise ProviderError(f"Yahoo rejected {symbol}: {description}")
        results = chart.get("result")
        if not isinstance(results, list) or not results:
            raise ProviderError(f"Yahoo returned no chart result for {symbol}")

        result = results[0]
        timestamps = result.get("timestamp")
        indicators = result.get("indicators")
        if not isinstance(timestamps, list) or not isinstance(indicators, dict):
            raise ProviderError(f"Yahoo returned no daily series for {symbol}")
        quote_series = indicators.get("quote")
        if not isinstance(quote_series, list) or not quote_series:
            raise ProviderError(f"Yahoo returned no quote series for {symbol}")
        quote = quote_series[0]

        opens = quote.get("open") or []
        highs = quote.get("high") or []
        lows = quote.get("low") or []
        closes = quote.get("close") or []
        volumes = quote.get("volume") or []

        bars: list[DailyBarRecord] = []
        for timestamp, open_value, high_value, low_value, close_value, volume_value in zip(
            timestamps,
            opens,
            highs,
            lows,
            closes,
            volumes,
            strict=False,
        ):
            if None in {open_value, high_value, low_value, close_value, volume_value}:
                continue
            trade_date = datetime.fromtimestamp(int(timestamp), tz=UTC).date()
            if trade_date < start_date or trade_date > end_date:
                continue
            bars.append(
                DailyBarRecord(
                    provider=self.name,
                    symbol=symbol,
                    trade_date=trade_date,
                    open=float(open_value),
                    high=float(high_value),
                    low=float(low_value),
                    close=float(close_value),
                    volume=int(float(volume_value)),
                )
            )

        corporate_actions: list[CorporateActionRecord] = []
        events = result.get("events")
        if isinstance(events, dict):
            dividends = events.get("dividends")
            if isinstance(dividends, dict):
                for event in dividends.values():
                    if not isinstance(event, dict):
                        continue
                    event_date = datetime.fromtimestamp(int(event["date"]), tz=UTC).date()
                    if event_date < start_date or event_date > end_date:
                        continue
                    amount = event.get("amount")
                    if amount is None:
                        continue
                    corporate_actions.append(
                        CorporateActionRecord(
                            provider=self.name,
                            symbol=symbol,
                            ex_date=event_date,
                            action_type="dividend",
                            value=float(amount),
                        )
                    )
            splits = events.get("splits")
            if isinstance(splits, dict):
                for event in splits.values():
                    if not isinstance(event, dict):
                        continue
                    event_date = datetime.fromtimestamp(int(event["date"]), tz=UTC).date()
                    if event_date < start_date or event_date > end_date:
                        continue
                    ratio = _split_ratio(event)
                    if ratio is None or ratio == 1.0:
                        continue
                    corporate_actions.append(
                        CorporateActionRecord(
                            provider=self.name,
                            symbol=symbol,
                            ex_date=event_date,
                            action_type="split",
                            value=ratio,
                        )
                    )

        return ProviderHistoryPayload(
            provider=self.name,
            symbol=symbol,
            domain="daily_prices",
            requested_at=requested_at,
            request_url=request_url,
            payload_format="json",
            raw_payload=raw_payload,
            bars=tuple(sorted(bars, key=lambda bar: bar.trade_date)),
            corporate_actions=tuple(sorted(corporate_actions, key=lambda action: action.ex_date)),
        )
