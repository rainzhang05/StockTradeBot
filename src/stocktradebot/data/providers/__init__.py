from __future__ import annotations

import os

from stocktradebot.config import AppConfig
from stocktradebot.data.providers.alpha_vantage import AlphaVantageDailyHistoryProvider
from stocktradebot.data.providers.base import DailyHistoryProvider, FundamentalsProvider
from stocktradebot.data.providers.sec import SecCompanyFactsProvider
from stocktradebot.data.providers.stooq import StooqDailyHistoryProvider


def build_provider_registry(config: AppConfig) -> dict[str, DailyHistoryProvider]:
    registry: dict[str, DailyHistoryProvider] = {}
    provider_map = config.data_providers.provider_map()

    stooq_config = provider_map["stooq"]
    if stooq_config.enabled:
        registry["stooq"] = StooqDailyHistoryProvider(
            base_url=stooq_config.base_url,
            timeout_seconds=stooq_config.timeout_seconds,
        )

    alpha_vantage_config = provider_map["alpha_vantage"]
    alpha_vantage_key = (
        os.getenv(alpha_vantage_config.api_key_env_var)
        if alpha_vantage_config.api_key_env_var
        else None
    )
    if alpha_vantage_config.enabled and alpha_vantage_key:
        registry["alpha_vantage"] = AlphaVantageDailyHistoryProvider(
            base_url=alpha_vantage_config.base_url,
            timeout_seconds=alpha_vantage_config.timeout_seconds,
            api_key=alpha_vantage_key,
        )

    return registry


def build_fundamentals_provider(config: AppConfig) -> FundamentalsProvider | None:
    provider_config = config.fundamentals_provider
    user_agent = provider_config.resolved_user_agent()
    if not provider_config.enabled or user_agent is None:
        return None

    return SecCompanyFactsProvider(
        base_url=provider_config.base_url,
        ticker_mapping_url=provider_config.ticker_mapping_url,
        timeout_seconds=provider_config.timeout_seconds,
        user_agent=user_agent,
        symbol_to_cik=provider_config.symbol_to_cik,
    )
