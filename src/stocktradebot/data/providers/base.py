from __future__ import annotations

from datetime import date
from typing import Protocol

from stocktradebot.data.models import FundamentalPayload, ProviderHistoryPayload


class ProviderError(RuntimeError):
    pass


class DailyHistoryProvider(Protocol):
    name: str

    def fetch_daily_history(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> ProviderHistoryPayload: ...


class FundamentalsProvider(Protocol):
    name: str

    def fetch_fundamentals(self, symbol: str) -> FundamentalPayload: ...
