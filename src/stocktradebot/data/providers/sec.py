from __future__ import annotations

import json
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from stocktradebot.data.models import FundamentalObservationRecord, FundamentalPayload
from stocktradebot.data.providers.base import ProviderError

SEC_METRIC_CONCEPTS: dict[str, tuple[tuple[str, str, str], ...]] = {
    "revenue": (
        ("us-gaap", "Revenues", "USD"),
        ("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax", "USD"),
        ("us-gaap", "SalesRevenueNet", "USD"),
    ),
    "net_income": (("us-gaap", "NetIncomeLoss", "USD"),),
    "operating_income": (("us-gaap", "OperatingIncomeLoss", "USD"),),
    "total_assets": (("us-gaap", "Assets", "USD"),),
    "total_liabilities": (("us-gaap", "Liabilities", "USD"),),
    "shareholders_equity": (
        ("us-gaap", "StockholdersEquity", "USD"),
        (
            "us-gaap",
            "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
            "USD",
        ),
    ),
    "shares_outstanding": (
        ("dei", "EntityCommonStockSharesOutstanding", "shares"),
        ("us-gaap", "CommonStockSharesOutstanding", "shares"),
    ),
    "operating_cash_flow": (
        ("us-gaap", "NetCashProvidedByUsedInOperatingActivities", "USD"),
        ("us-gaap", "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations", "USD"),
    ),
    "capital_expenditures": (
        ("us-gaap", "PaymentsToAcquirePropertyPlantAndEquipment", "USD"),
        ("us-gaap", "CapitalExpendituresIncurredButNotYetPaid", "USD"),
    ),
}


def _parse_sec_datetime(value: str) -> datetime:
    if "T" in value:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        parsed = datetime.fromisoformat(f"{value}T23:59:59+00:00")
    return parsed.astimezone(UTC)


class SecCompanyFactsProvider:
    name = "sec_companyfacts"

    def __init__(
        self,
        *,
        base_url: str,
        ticker_mapping_url: str,
        timeout_seconds: float,
        user_agent: str,
        symbol_to_cik: dict[str, str] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.ticker_mapping_url = ticker_mapping_url
        self.timeout_seconds = timeout_seconds
        self.user_agent = user_agent
        self.symbol_to_cik = {
            symbol.upper(): cik.zfill(10) for symbol, cik in (symbol_to_cik or {}).items()
        }
        self._cached_mapping: dict[str, str] | None = None

    def _read_url(self, url: str) -> tuple[str, datetime]:
        request = Request(url, headers={"User-Agent": self.user_agent})
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                raw_payload = response.read().decode("utf-8")
                requested_at_header = response.headers.get("Date")
        except HTTPError as exc:  # pragma: no cover - live network only
            raise ProviderError(f"SEC request failed: HTTP {exc.code}") from exc
        except URLError as exc:  # pragma: no cover - live network only
            raise ProviderError(f"SEC request failed: {exc.reason}") from exc

        if requested_at_header:
            requested_at = parsedate_to_datetime(requested_at_header).astimezone(UTC)
        else:
            requested_at = datetime.now(UTC)
        return raw_payload, requested_at

    def _ticker_mapping(self) -> dict[str, str]:
        if self._cached_mapping is not None:
            return self._cached_mapping

        raw_payload, _ = self._read_url(self.ticker_mapping_url)
        payload = json.loads(raw_payload)
        if not isinstance(payload, dict):
            raise ProviderError("SEC ticker mapping payload was not a JSON object")

        mapping: dict[str, str] = {}
        for item in payload.values():
            if not isinstance(item, dict):
                continue
            ticker = item.get("ticker")
            cik = item.get("cik_str")
            if ticker is None or cik is None:
                continue
            mapping[str(ticker).upper()] = str(cik).zfill(10)

        self._cached_mapping = mapping
        return mapping

    def _resolve_cik(self, symbol: str) -> str:
        normalized_symbol = symbol.upper()
        if normalized_symbol in self.symbol_to_cik:
            return self.symbol_to_cik[normalized_symbol]

        mapping = self._ticker_mapping()
        if normalized_symbol not in mapping:
            raise ProviderError(f"SEC ticker mapping has no CIK for {symbol}")
        return mapping[normalized_symbol]

    def fetch_fundamentals(self, symbol: str) -> FundamentalPayload:
        cik = self._resolve_cik(symbol)
        request_url = f"{self.base_url}/CIK{cik}.json"
        raw_payload, requested_at = self._read_url(request_url)
        payload = json.loads(raw_payload)

        facts = payload.get("facts")
        if not isinstance(facts, dict):
            raise ProviderError(f"SEC company facts payload missing facts for {symbol}")

        observations: list[FundamentalObservationRecord] = []
        for metric_name, candidates in SEC_METRIC_CONCEPTS.items():
            for taxonomy, concept_name, unit_name in candidates:
                taxonomy_facts = facts.get(taxonomy)
                if not isinstance(taxonomy_facts, dict):
                    continue
                concept = taxonomy_facts.get(concept_name)
                if not isinstance(concept, dict):
                    continue
                units = concept.get("units", {})
                unit_rows = units.get(unit_name)
                if not isinstance(unit_rows, list):
                    continue
                for row in unit_rows:
                    end_value = row.get("end")
                    filed_value = row.get("filed")
                    numeric_value = row.get("val")
                    if end_value is None or filed_value is None or numeric_value is None:
                        continue
                    try:
                        value = float(numeric_value)
                    except (TypeError, ValueError):
                        continue

                    fp_value = row.get("fp")
                    form_type = None if row.get("form") is None else str(row.get("form"))
                    fiscal_period_type = (
                        str(fp_value).upper()
                        if fp_value is not None
                        else ("FY" if form_type == "10-K" else "Q?")
                    )
                    observations.append(
                        FundamentalObservationRecord(
                            provider=self.name,
                            symbol=symbol,
                            metric_name=metric_name,
                            source_concept=concept_name,
                            fiscal_period_end=_parse_sec_datetime(str(end_value)).date(),
                            fiscal_period_type=fiscal_period_type,
                            filed_at=_parse_sec_datetime(str(filed_value)),
                            available_at=_parse_sec_datetime(str(filed_value)),
                            unit=unit_name,
                            value=value,
                            form_type=form_type,
                            accession=(
                                None
                                if row.get("accn") is None
                                else str(row.get("accn")).replace("-", "")
                            ),
                        )
                    )
                break

        return FundamentalPayload(
            provider=self.name,
            symbol=symbol,
            domain="fundamentals",
            requested_at=requested_at,
            request_url=request_url,
            payload_format="json",
            raw_payload=raw_payload,
            observations=tuple(
                sorted(
                    observations,
                    key=lambda observation: (
                        observation.metric_name,
                        observation.available_at,
                        observation.fiscal_period_end,
                    ),
                )
            ),
            metadata={"cik": cik},
        )
