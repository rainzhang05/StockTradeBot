from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
CONFIG_FILENAME = "config.json"
DEFAULT_STOOQ_BASE_URL = "https://stooq.com"
DEFAULT_ALPHA_VANTAGE_BASE_URL = "https://www.alphavantage.co"
DEFAULT_SEC_COMPANY_FACTS_BASE_URL = "https://data.sec.gov/api/xbrl/companyfacts"
DEFAULT_SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"


def resolve_app_home(app_home: Path | None = None) -> Path:
    if app_home is not None:
        return app_home.expanduser().resolve()

    env_home = os.getenv("STOCKTRADEBOT_HOME")
    if env_home:
        return Path(env_home).expanduser().resolve()

    return (Path.home() / ".stocktradebot").resolve()


@dataclass(slots=True)
class ValidationThresholds:
    ohlc_relative_tolerance: float = 0.0025
    volume_relative_tolerance: float = 0.05

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None = None) -> ValidationThresholds:
        defaults = cls()
        if data is None:
            return defaults

        return cls(
            ohlc_relative_tolerance=float(
                data.get("ohlc_relative_tolerance", defaults.ohlc_relative_tolerance)
            ),
            volume_relative_tolerance=float(
                data.get("volume_relative_tolerance", defaults.volume_relative_tolerance)
            ),
        )

    def to_dict(self) -> dict[str, float]:
        return {
            "ohlc_relative_tolerance": self.ohlc_relative_tolerance,
            "volume_relative_tolerance": self.volume_relative_tolerance,
        }


@dataclass(slots=True)
class ProviderConfig:
    enabled: bool
    priority: int
    base_url: str
    timeout_seconds: float = 20.0
    api_key_env_var: str | None = None
    rate_limit_per_minute: int | None = None

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any] | None,
        *,
        defaults: ProviderConfig,
    ) -> ProviderConfig:
        if data is None:
            return defaults

        api_key_env_var = data.get("api_key_env_var", defaults.api_key_env_var)
        return cls(
            enabled=bool(data.get("enabled", defaults.enabled)),
            priority=int(data.get("priority", defaults.priority)),
            base_url=str(data.get("base_url", defaults.base_url)),
            timeout_seconds=float(data.get("timeout_seconds", defaults.timeout_seconds)),
            api_key_env_var=None if api_key_env_var is None else str(api_key_env_var),
            rate_limit_per_minute=(
                int(data["rate_limit_per_minute"])
                if data.get("rate_limit_per_minute") is not None
                else defaults.rate_limit_per_minute
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "priority": self.priority,
            "base_url": self.base_url,
            "timeout_seconds": self.timeout_seconds,
            "api_key_env_var": self.api_key_env_var,
            "rate_limit_per_minute": self.rate_limit_per_minute,
        }


def default_stooq_provider() -> ProviderConfig:
    return ProviderConfig(
        enabled=True,
        priority=1,
        base_url=DEFAULT_STOOQ_BASE_URL,
        timeout_seconds=20.0,
    )


def default_alpha_vantage_provider() -> ProviderConfig:
    return ProviderConfig(
        enabled=False,
        priority=2,
        base_url=DEFAULT_ALPHA_VANTAGE_BASE_URL,
        timeout_seconds=20.0,
        api_key_env_var="ALPHAVANTAGE_API_KEY",
        rate_limit_per_minute=5,
    )


@dataclass(slots=True)
class DataProvidersConfig:
    primary_provider: str = "stooq"
    secondary_provider: str | None = None
    validation: ValidationThresholds = field(default_factory=ValidationThresholds)
    stooq: ProviderConfig = field(default_factory=default_stooq_provider)
    alpha_vantage: ProviderConfig = field(default_factory=default_alpha_vantage_provider)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None = None) -> DataProvidersConfig:
        defaults = cls()
        if data is None:
            return defaults

        secondary_provider = data.get("secondary_provider", defaults.secondary_provider)
        return cls(
            primary_provider=str(data.get("primary_provider", defaults.primary_provider)),
            secondary_provider=None if secondary_provider is None else str(secondary_provider),
            validation=ValidationThresholds.from_dict(data.get("validation")),
            stooq=ProviderConfig.from_dict(data.get("stooq"), defaults=defaults.stooq),
            alpha_vantage=ProviderConfig.from_dict(
                data.get("alpha_vantage"),
                defaults=defaults.alpha_vantage,
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "primary_provider": self.primary_provider,
            "secondary_provider": self.secondary_provider,
            "validation": self.validation.to_dict(),
            "stooq": self.stooq.to_dict(),
            "alpha_vantage": self.alpha_vantage.to_dict(),
        }

    def provider_map(self) -> dict[str, ProviderConfig]:
        return {
            "stooq": self.stooq,
            "alpha_vantage": self.alpha_vantage,
        }


@dataclass(slots=True)
class UniverseConfig:
    max_stocks: int = 300
    min_price: float = 5.0
    min_history_days: int = 20
    liquidity_lookback_days: int = 20
    monthly_refresh_day: int = 1
    stock_candidates: list[str] = field(default_factory=list)
    curated_etfs: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None = None) -> UniverseConfig:
        defaults = cls()
        if data is None:
            return defaults

        return cls(
            max_stocks=int(data.get("max_stocks", defaults.max_stocks)),
            min_price=float(data.get("min_price", defaults.min_price)),
            min_history_days=int(data.get("min_history_days", defaults.min_history_days)),
            liquidity_lookback_days=int(
                data.get("liquidity_lookback_days", defaults.liquidity_lookback_days)
            ),
            monthly_refresh_day=int(data.get("monthly_refresh_day", defaults.monthly_refresh_day)),
            stock_candidates=[str(symbol) for symbol in data.get("stock_candidates", [])],
            curated_etfs=[str(symbol) for symbol in data.get("curated_etfs", [])],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_stocks": self.max_stocks,
            "min_price": self.min_price,
            "min_history_days": self.min_history_days,
            "liquidity_lookback_days": self.liquidity_lookback_days,
            "monthly_refresh_day": self.monthly_refresh_day,
            "stock_candidates": self.stock_candidates,
            "curated_etfs": self.curated_etfs,
        }


@dataclass(slots=True)
class FundamentalsProviderConfig:
    enabled: bool = False
    base_url: str = DEFAULT_SEC_COMPANY_FACTS_BASE_URL
    ticker_mapping_url: str = DEFAULT_SEC_TICKERS_URL
    timeout_seconds: float = 20.0
    user_agent_env_var: str = "SEC_USER_AGENT"
    user_agent: str | None = None
    symbol_to_cik: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None = None) -> FundamentalsProviderConfig:
        defaults = cls()
        if data is None:
            return defaults

        user_agent = data.get("user_agent", defaults.user_agent)
        symbol_to_cik = {
            str(symbol).upper(): str(cik).zfill(10)
            for symbol, cik in data.get("symbol_to_cik", {}).items()
        }
        return cls(
            enabled=bool(data.get("enabled", defaults.enabled)),
            base_url=str(data.get("base_url", defaults.base_url)),
            ticker_mapping_url=str(data.get("ticker_mapping_url", defaults.ticker_mapping_url)),
            timeout_seconds=float(data.get("timeout_seconds", defaults.timeout_seconds)),
            user_agent_env_var=str(data.get("user_agent_env_var", defaults.user_agent_env_var)),
            user_agent=None if user_agent is None else str(user_agent),
            symbol_to_cik=symbol_to_cik,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "base_url": self.base_url,
            "ticker_mapping_url": self.ticker_mapping_url,
            "timeout_seconds": self.timeout_seconds,
            "user_agent_env_var": self.user_agent_env_var,
            "user_agent": self.user_agent,
            "symbol_to_cik": self.symbol_to_cik,
        }

    def resolved_user_agent(self) -> str | None:
        env_user_agent = os.getenv(self.user_agent_env_var)
        if env_user_agent:
            return env_user_agent
        return self.user_agent


@dataclass(slots=True)
class ModelTrainingConfig:
    feature_set_version: str = "daily-core-v1"
    label_version: str = "forward-return-v1"
    benchmark_symbol: str = "SPY"
    min_feature_history_days: int = 60
    min_label_history_days: int = 10
    dataset_lookback_days: int = 400

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None = None) -> ModelTrainingConfig:
        defaults = cls()
        if data is None:
            return defaults

        return cls(
            feature_set_version=str(data.get("feature_set_version", defaults.feature_set_version)),
            label_version=str(data.get("label_version", defaults.label_version)),
            benchmark_symbol=str(data.get("benchmark_symbol", defaults.benchmark_symbol)).upper(),
            min_feature_history_days=int(
                data.get("min_feature_history_days", defaults.min_feature_history_days)
            ),
            min_label_history_days=int(
                data.get("min_label_history_days", defaults.min_label_history_days)
            ),
            dataset_lookback_days=int(
                data.get("dataset_lookback_days", defaults.dataset_lookback_days)
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_set_version": self.feature_set_version,
            "label_version": self.label_version,
            "benchmark_symbol": self.benchmark_symbol,
            "min_feature_history_days": self.min_feature_history_days,
            "min_label_history_days": self.min_label_history_days,
            "dataset_lookback_days": self.dataset_lookback_days,
        }


@dataclass(slots=True)
class AppConfig:
    app_home: Path
    config_path: Path
    database_path: Path
    artifacts_dir: Path
    logs_dir: Path
    api_host: str = DEFAULT_HOST
    api_port: int = DEFAULT_PORT
    open_browser_on_launch: bool = True
    timezone: str = "local"
    data_providers: DataProvidersConfig = field(default_factory=DataProvidersConfig)
    fundamentals_provider: FundamentalsProviderConfig = field(
        default_factory=FundamentalsProviderConfig
    )
    universe: UniverseConfig = field(default_factory=UniverseConfig)
    model_training: ModelTrainingConfig = field(default_factory=ModelTrainingConfig)

    @classmethod
    def default(cls, app_home: Path | None = None) -> AppConfig:
        resolved_home = resolve_app_home(app_home)
        return cls(
            app_home=resolved_home,
            config_path=resolved_home / CONFIG_FILENAME,
            database_path=resolved_home / "runtime" / "stocktradebot.sqlite3",
            artifacts_dir=resolved_home / "artifacts",
            logs_dir=resolved_home / "logs",
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any], app_home: Path | None = None) -> AppConfig:
        defaults = cls.default(app_home)
        return cls(
            app_home=defaults.app_home,
            config_path=defaults.config_path,
            database_path=Path(data.get("database_path", defaults.database_path)).expanduser(),
            artifacts_dir=Path(data.get("artifacts_dir", defaults.artifacts_dir)).expanduser(),
            logs_dir=Path(data.get("logs_dir", defaults.logs_dir)).expanduser(),
            api_host=str(data.get("api_host", defaults.api_host)),
            api_port=int(data.get("api_port", defaults.api_port)),
            open_browser_on_launch=bool(
                data.get("open_browser_on_launch", defaults.open_browser_on_launch)
            ),
            timezone=str(data.get("timezone", defaults.timezone)),
            data_providers=DataProvidersConfig.from_dict(data.get("data_providers")),
            fundamentals_provider=FundamentalsProviderConfig.from_dict(
                data.get("fundamentals_provider")
            ),
            universe=UniverseConfig.from_dict(data.get("universe")),
            model_training=ModelTrainingConfig.from_dict(data.get("model_training")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "database_path": str(self.database_path),
            "artifacts_dir": str(self.artifacts_dir),
            "logs_dir": str(self.logs_dir),
            "api_host": self.api_host,
            "api_port": self.api_port,
            "open_browser_on_launch": self.open_browser_on_launch,
            "timezone": self.timezone,
            "data_providers": self.data_providers.to_dict(),
            "fundamentals_provider": self.fundamentals_provider.to_dict(),
            "universe": self.universe.to_dict(),
            "model_training": self.model_training.to_dict(),
        }

    def database_url(self) -> str:
        return f"sqlite+pysqlite:///{self.database_path}"

    @property
    def raw_payload_dir(self) -> Path:
        return self.artifacts_dir / "raw-provider-payloads"

    @property
    def dataset_artifacts_dir(self) -> Path:
        return self.artifacts_dir / "datasets"

    def ensure_runtime_dirs(self) -> None:
        self.app_home.mkdir(parents=True, exist_ok=True)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.raw_payload_dir.mkdir(parents=True, exist_ok=True)
        self.dataset_artifacts_dir.mkdir(parents=True, exist_ok=True)

    def save(self) -> None:
        self.ensure_runtime_dirs()
        self.config_path.write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8")


def load_config(app_home: Path | None = None) -> AppConfig:
    defaults = AppConfig.default(app_home)
    if not defaults.config_path.exists():
        return defaults

    data = json.loads(defaults.config_path.read_text(encoding="utf-8"))
    return AppConfig.from_dict(data, app_home=defaults.app_home)


def initialize_config(app_home: Path | None = None, *, overwrite: bool = False) -> AppConfig:
    config = AppConfig.default(app_home)
    if config.config_path.exists() and not overwrite:
        return load_config(app_home)

    config.save()
    return config
