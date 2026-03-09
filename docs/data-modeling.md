# StockTradeBot Data and Modeling Specification

This document defines how the repository handles market data, fundamentals, features, labels, and reproducibility.

## 1. Data Architecture Principles

The system must separate:

1. raw provider payloads
2. normalized provider records
3. validated canonical market data
4. feature-ready research tables
5. point-in-time dataset snapshots
6. model-linked artifacts and reports

Every step must preserve provenance and be reproducible.

## 2. Supported Data Domains

V1 requires:

- daily OHLCV bars for the dynamic stock universe
- daily OHLCV bars for curated ETFs
- corporate actions needed for adjusted prices
- market index/reference series for regime features and benchmarks
- approximate point-in-time fundamentals derived from free filings data
- universe membership snapshots

Planned later:

- promotable intraday history for 15-minute and 1-hour features
- richer live quote and order-book aware execution data

## 3. Universe Rules

Target universe policy:

- dynamic universe of approximately the top 300 liquid U.S. common stocks
- separate curated ETF list for broad market, sector, and defensive allocation use

Universe exclusions:

- penny stocks
- ADRs
- recent IPOs without enough history
- low-liquidity names
- leveraged ETFs
- inverse ETFs

Universe construction rules:

- rebuild on a scheduled cadence, initially monthly
- rank candidates using trailing liquidity and price filters
- persist each snapshot with an effective date
- use historical snapshots in research to prevent look-ahead bias

## 4. Provider Adapter Model

Each external data source must be wrapped in an adapter exposing:

- provider identifier
- supported data domains
- symbol resolution and identifier mapping
- fetch methods for bars, corporate actions, and fundamentals
- request metadata and rate-limit metadata
- normalization into internal schemas

Providers may differ by domain. A source suitable for prices does not automatically qualify as a fundamentals source.

## 5. Canonicalization Policy

The repository does not trust a single free provider as universally authoritative.

### 5.1 Validation Tiers

Each normalized record must be assigned one of:

- `verified`
  - corroborated by provider agreement or passed a domain-specific validation rule with no conflicts
- `provisional`
  - internally consistent but not sufficiently corroborated for promotable datasets
- `quarantined`
  - conflicts with another provider or fails sanity checks

Only `verified` data may enter feature-ready datasets used for paper or live promotion decisions.

### 5.2 Price-Bar Agreement Rules

For daily bars:

- prefer one configured primary provider value only after it agrees with at least one secondary source within tolerance
- compare date alignment, split-adjustment state, and OHLCV ranges before accepting a bar
- quarantine bars with material deviation instead of averaging or silently choosing one
- attempt repair only through a documented reconciliation step

Default agreement tolerances:

- open/high/low/close relative difference: `<= 0.25%`
- volume relative difference: `<= 5%`
- exact date match required

If no confirming source is available, a bar may remain `provisional` for development use but must not enter promotable datasets or live-critical workflows.

### 5.3 Corporate Actions

Splits and dividends must be stored explicitly and linked to adjusted-series generation. Adjustment logic must be deterministic and repeatable.

### 5.4 Data-Quality Incidents

Any unresolved discrepancy must create a persisted incident record with:

- symbol
- date
- field(s) affected
- involved providers
- observed values
- resolution status
- operator notes if manually reviewed

## 6. Fundamentals Policy

V1 fundamentals use free SEC-derived data with conservative availability handling.

Rules:

- use filing acceptance or clear public availability timestamps as the earliest usable time
- never backfill a fundamental value into dates before the filing was available
- maintain both raw reported values and derived ratios
- drop a feature when its as-of validity is uncertain rather than guessing
- preserve restatement history instead of rewriting prior snapshots

Initial v1 fundamentals focus:

- revenue
- net income
- operating income
- free cash flow when derivable
- total assets
- total liabilities
- shareholders’ equity
- shares outstanding when available

Initial derived ratios:

- earnings yield
- sales yield
- book-to-price
- debt-to-equity
- asset growth
- accrual-style quality proxy

## 7. Feature System

Required feature families:

- momentum over multiple windows
- mean reversion over short windows
- realized volatility
- downside volatility and drawdown measures
- volume and liquidity proxies
- cross-sectional relative strength
- sector-relative performance
- benchmark-relative performance
- regime indicators derived from market behavior
- fundamental ratios and change metrics

Feature governance rules:

- every feature has a documented name, formula, window set, null policy, and normalization rule
- feature sets are versioned
- changes to formulas or defaults require a new feature-set version
- feature computation must be deterministic and batch reproducible

## 8. Label Definitions

V1 baseline labels:

- primary ranking label: 5-trading-day forward total return, cross-sectionally standardized within the active universe snapshot
- secondary diagnostic label: 10-trading-day forward total return
- risk diagnostic label: 10-trading-day forward max drawdown

Label rules:

- labels are computed from verified adjusted prices only
- labels must align to the decision timestamp and available data at that time
- label versions are explicit and stored with datasets and models

## 9. Dataset Versioning and Lineage

Every dataset snapshot must record:

- universe snapshot ID
- provider versions and extract time ranges
- canonicalization rules version
- feature set version
- label version
- generation code version
- generation timestamp
- row counts and null statistics

Every trained model must link back to exactly one dataset snapshot.

## 10. Model Family and Registry Expectations

Production model families:

- linear models
- boosting models
- ensemble combinations of those families

Registry metadata must include:

- model ID and semantic version
- training window
- dataset snapshot ID
- feature set version
- label version
- training code revision
- validation metrics
- benchmark comparisons
- regime-split results
- paper-trading status
- promotion status

## 11. Research Cadence

Baseline training policy:

- scheduled retraining every two weeks
- earlier retraining allowed when a documented performance trigger fires

No model may be promoted automatically. Validation and promotion review remain explicit steps.

## 12. Daily-First V1 and Intraday Expansion

Daily-first means:

- v1 must produce promotable datasets, models, backtests, paper runs, and live/manual workflows from daily data alone
- intraday-aware execution logic may still exist, but promotable alpha does not depend on historical intraday breadth in v1

Intraday expansion phase must add:

- free-source feasibility review
- 15-minute and 1-hour canonicalization rules
- intraday feature versions
- separate validation proving intraday data quality is good enough for promotion

Intraday support is not complete until that later phase exits successfully.
