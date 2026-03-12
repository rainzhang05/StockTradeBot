from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from stocktradebot.research import run_research_optimization


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the daily research optimization sweep.")
    parser.add_argument(
        "--source-app-home",
        type=Path,
        default=None,
        help="Path to the source StockTradeBot app home. Defaults to ~/.stocktradebot.",
    )
    parser.add_argument(
        "--output-path",
        type=Path,
        default=None,
        help="Optional path for the final optimization report JSON.",
    )
    parser.add_argument(
        "--isolated-root",
        type=Path,
        default=None,
        help="Optional directory where the isolated copied app home should be created.",
    )
    parser.add_argument(
        "--as-of",
        type=date.fromisoformat,
        default=None,
        help="Optional YYYY-MM-DD date override for the optimization run.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    summary = run_research_optimization(
        source_app_home=args.source_app_home,
        output_path=args.output_path,
        isolated_root=args.isolated_root,
        as_of_date=args.as_of,
    )
    best_run = summary.best_run
    print(f"report_path={summary.output_path}")
    print(f"isolated_app_home={summary.isolated_app_home}")
    print(f"as_of_date={summary.as_of_date.isoformat()}")
    if best_run is None:
        print("best_total_return=unavailable")
        print(f"baseline_total_return={summary.baseline.total_return}")
        return 1
    print(f"baseline_total_return={summary.baseline.total_return:.6f}")
    print(f"best_total_return={best_run.total_return:.6f}")
    print(f"best_benchmark_return={best_run.benchmark_return:.6f}")
    print(f"best_excess_return={best_run.excess_return:.6f}")
    print(f"best_max_drawdown={best_run.max_drawdown:.6f}")
    print(f"best_turnover_ratio={best_run.turnover_ratio:.6f}")
    print(f"best_trade_count={best_run.trade_count}")
    print(f"best_average_positions={best_run.average_positions:.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
