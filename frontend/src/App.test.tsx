import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import type { WorkspaceSnapshot } from "./types";

function createWorkspace(): WorkspaceSnapshot {
  const paper = {
    mode_state: {
      current_mode: "simulation",
      requested_mode: null,
      live_profile: "manual",
      is_frozen: false,
      active_freeze_event_id: null,
      freeze_reason: null,
      metadata: {},
      updated_at: "2026-03-09T10:00:00Z"
    },
    latest_run: null,
    paper_safe_days: 12,
    active_freeze: null,
    broker: {
      configured: false,
      provider: "ibkr-client-portal",
      message: "broker integration disabled in config",
      paper_account_id: "DU1234567",
      live_account_id: "U1234567",
      gateway: { base_url: "https://127.0.0.1:5000/v1/api" },
      connectivity: null,
      accounts: []
    }
  };
  const live = {
    mode_state: {
      current_mode: "simulation",
      requested_mode: null,
      live_profile: "manual",
      is_frozen: false,
      active_freeze_event_id: null,
      freeze_reason: null,
      metadata: {},
      updated_at: "2026-03-09T10:00:00Z"
    },
    latest_run: { id: 21, status: "pending-approval", mode: "live-manual", as_of_date: "2026-04-15", decision_date: "2026-04-15", model_entry_id: 7, dataset_snapshot_id: 4, regime: "neutral", gross_exposure_target: 0.7, gross_exposure_actual: 0.7, start_nav: 100000, end_nav: 100050, cash_start: 100000, cash_end: 82000, artifact_path: "artifacts/live.json", summary: {}, error_message: null, created_at: "2026-04-15T15:50:00Z", completed_at: "2026-04-15T15:52:00Z" },
    latest_approvals: [
      {
        approval_id: 8,
        order_intent_id: 55,
        broker_order_id: null,
        symbol: "AAPL",
        mode: "live-manual",
        status: "pending",
        requested_by: "local-operator",
        decided_by: null,
        reason: null,
        metadata: {},
        created_at: "2026-04-15T15:52:00Z",
        decided_at: null
      }
    ],
    broker: {
      configured: false,
      provider: "ibkr-client-portal",
      message: "broker integration disabled in config",
      paper_account_id: "DU1234567",
      live_account_id: "U1234567",
      gateway: { base_url: "https://127.0.0.1:5000/v1/api" },
      connectivity: null,
      accounts: []
    },
    gates: {
      manual: { allowed: true, checks: [{ name: "broker-ready", ok: true, detail: "paper history sufficient" }] },
      autonomous: { allowed: false, checks: [{ name: "autonomous-safe-days", ok: false, detail: "need 60 safe days" }] }
    },
    safe_day_counts: { paper: 12, paper_and_live: 12 },
    active_freeze: null
  };

  return {
    health: {
      status: "ok",
      version: "0.1.0",
      mode: "simulation",
      ui_url: "http://127.0.0.1:8000",
      checks: [
        { name: "primary-provider", ok: true, detail: "stooq" },
        { name: "fundamentals-provider", ok: true, detail: "SEC ready" }
      ]
    },
    setup: {
      initialized: true,
      config_path: "/tmp/config.json",
      database_path: "/tmp/runtime.sqlite3"
    },
    config: {
      timezone: "local",
      database_path: "/tmp/runtime.sqlite3",
      artifacts_dir: "/tmp/artifacts",
      logs_dir: "/tmp/logs",
      data_providers: {
        primary_provider: "stooq",
        secondary_provider: "alpha_vantage",
        alpha_vantage: { enabled: true }
      },
      fundamentals_provider: {
        enabled: true,
        user_agent: "StockTradeBot/test"
      },
      universe: {
        stock_candidates: ["AAPL", "MSFT"],
        curated_etfs: ["SPY"]
      },
      broker: {
        enabled: false,
        operator_name: "local-operator",
        paper_account_id: "DU1234567",
        live_account_id: "U1234567",
        gateway: { base_url: "https://127.0.0.1:5000/v1/api" }
      },
      execution: {
        default_mode: "simulation",
        live_profile: "manual"
      },
      risk: {
        daily_loss_cap: 0.03,
        drawdown_freeze: 0.2
      }
    },
    system: {
      status: {
        mode: "simulation",
        schema_version: "phase6",
        app_home: "/tmp/stocktradebot"
      },
      audit_events: [{ id: 1, category: "runtime", message: "runtime prepared", created_at: "2026-03-09T10:00:00Z" }]
    },
    broker: {
      paper,
      live
    },
    market_data: {
      latest_run: {
        id: 4,
        status: "completed",
        as_of_date: "2026-04-15",
        primary_provider: "stooq",
        secondary_provider: "alpha_vantage",
        summary: {},
        completed_at: "2026-04-15T15:00:00Z"
      },
      latest_universe_snapshot: {
        id: 3,
        effective_date: "2026-04-15",
        stock_count: 2,
        etf_count: 1,
        selection_version: "v1",
        summary: {}
      },
      validation_counts: {
        verified: 180,
        provisional: 20
      },
      fundamentals_observation_count: 48,
      recent_incidents: []
    },
    datasets: {
      latest_dataset_snapshot: {
        id: 4,
        as_of_date: "2026-04-15",
        universe_snapshot_id: 3,
        feature_set_version: "daily-core-v1",
        label_version: "forward-return-v1",
        row_count: 280,
        artifact_path: "artifacts/datasets/daily.json",
        null_statistics: {},
        metadata: {},
        created_at: "2026-04-15T15:10:00Z"
      },
      feature_set_versions: [{ version: "daily-core-v1", definition: {}, created_at: "2026-03-09T10:00:00Z" }],
      label_versions: [{ version: "forward-return-v1", definition: {}, created_at: "2026-03-09T10:00:00Z" }],
      fundamentals_observation_count: 48
    },
    models: {
      latest_training_run: {
        id: 6,
        status: "completed",
        as_of_date: "2026-04-15",
        dataset_snapshot_id: 4,
        model_family: "linear-correlation-v1",
        model_version: "linear-correlation-v1-test",
        summary: {},
        error_message: null,
        created_at: "2026-04-15T15:15:00Z",
        completed_at: "2026-04-15T15:16:00Z"
      },
      latest_model: {
        id: 7,
        version: "linear-correlation-v1-test",
        family: "linear",
        dataset_snapshot_id: 4,
        feature_set_version: "daily-core-v1",
        label_version: "forward-return-v1",
        training_start_date: "2025-11-01",
        training_end_date: "2026-04-15",
        training_row_count: 280,
        artifact_path: "artifacts/models/model.json",
        metrics: { total_return: 0.12 },
        benchmark_metrics: { benchmark_return: 0.06 },
        promotion_status: "candidate",
        promotion_reasons: [],
        created_at: "2026-04-15T15:16:00Z"
      },
      latest_validation_run: {
        id: 9,
        status: "completed",
        dataset_snapshot_id: 4,
        model_entry_id: 7,
        fold_count: 4,
        artifact_path: "artifacts/reports/validation.json",
        summary: {},
        error_message: null,
        created_at: "2026-04-15T15:17:00Z",
        completed_at: "2026-04-15T15:18:00Z"
      },
      latest_backtest_run: {
        id: 10,
        status: "completed",
        mode: "static-model",
        dataset_snapshot_id: 4,
        model_entry_id: 7,
        benchmark_symbol: "SPY",
        start_date: "2026-01-01",
        end_date: "2026-04-15",
        artifact_path: "artifacts/reports/backtest.json",
        summary: {},
        error_message: null,
        created_at: "2026-04-15T15:20:00Z",
        completed_at: "2026-04-15T15:21:00Z"
      }
    },
    risk: {
      mode_state: {
        current_mode: "simulation",
        requested_mode: null,
        live_profile: "manual",
        is_frozen: false,
        active_freeze_event_id: null,
        freeze_reason: null,
        metadata: {},
        updated_at: "2026-03-09T10:00:00Z"
      },
      active_freeze: null
    },
    portfolio: {
      status: {
        mode_state: {
          current_mode: "simulation",
          requested_mode: null,
          live_profile: "manual",
          is_frozen: false,
          active_freeze_event_id: null,
          freeze_reason: null,
          metadata: {},
          updated_at: "2026-03-09T10:00:00Z"
        },
        active_freeze: null,
        latest_run: {
          id: 11,
          status: "completed",
          mode: "simulation",
          as_of_date: "2026-04-15",
          decision_date: "2026-04-15",
          model_entry_id: 7,
          dataset_snapshot_id: 4,
          regime: "risk-on",
          gross_exposure_target: 0.7,
          gross_exposure_actual: 0.69,
          start_nav: 100000,
          end_nav: 100240,
          cash_start: 100000,
          cash_end: 78000,
          artifact_path: "artifacts/reports/simulation.json",
          summary: {},
          error_message: null,
          created_at: "2026-04-15T15:25:00Z",
          completed_at: "2026-04-15T15:26:00Z"
        },
        latest_target_snapshot: {
          id: 12,
          simulation_run_id: 11,
          trade_date: "2026-04-15",
          nav: 100240,
          cash_balance: 78000,
          gross_exposure: 0.69,
          net_exposure: 0.69,
          holding_count: 2,
          turnover_ratio: 0.12,
          positions: [
            {
              symbol: "AAPL",
              target_weight: 0.1,
              actual_weight: 0.1,
              shares: 75,
              price: 188.5,
              market_value: 14137.5,
              score: 0.84,
              sector: "Technology",
              metadata: {}
            },
            {
              symbol: "MSFT",
              target_weight: 0.09,
              actual_weight: 0.09,
              shares: 34,
              price: 416.2,
              market_value: 14150.8,
              score: 0.72,
              sector: "Technology",
              metadata: {}
            }
          ]
        }
      },
      latest_target_snapshot: {
        id: 12,
        simulation_run_id: 11,
        trade_date: "2026-04-15",
        nav: 100240,
        cash_balance: 78000,
        gross_exposure: 0.69,
        net_exposure: 0.69,
        holding_count: 2,
        turnover_ratio: 0.12,
        positions: [
          {
            symbol: "AAPL",
            target_weight: 0.1,
            actual_weight: 0.1,
            shares: 75,
            price: 188.5,
            market_value: 14137.5,
            score: 0.84,
            sector: "Technology",
            metadata: {}
          }
        ]
      },
      latest_orders: [
        {
          id: 5,
          symbol: "AAPL",
          side: "buy",
          status: "submitted",
          order_type: "limit",
          requested_shares: 20,
          requested_notional: 3750,
          limit_price: 187.5,
          reference_price: 188.5,
          expected_slippage_bps: 4,
          target_weight: 0.1,
          metadata: {},
          created_at: "2026-04-15T15:30:00Z",
          completed_at: null
        }
      ],
      latest_fills: [
        {
          id: 3,
          order_intent_id: 5,
          symbol: "AAPL",
          side: "buy",
          fill_status: "filled",
          filled_shares: 20,
          filled_notional: 3750,
          fill_price: 187.5,
          commission: 1.5,
          slippage_bps: 3.5,
          expected_spread_bps: 2,
          metadata: {},
          filled_at: "2026-04-15T15:31:00Z"
        }
      ]
    },
    paper,
    live
  } as WorkspaceSnapshot;
}

describe("App", () => {
  let workspace = createWorkspace();

  beforeEach(() => {
    workspace = createWorkspace();
    window.location.hash = "";
    globalThis.fetch = vi.fn(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/api/v1/operator/workspace")) {
        return new Response(JSON.stringify(workspace), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }

      if (url.endsWith("/api/v1/config")) {
        const payload = JSON.parse(String(init?.body ?? "{}")) as Record<string, unknown>;
        workspace.config = {
          ...workspace.config,
          timezone: payload.timezone ?? workspace.config.timezone
        };
        return new Response(JSON.stringify({ config: workspace.config }), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }

      if (url.includes("/api/v1/live/approvals")) {
        workspace.live.latest_approvals = [];
        return new Response(JSON.stringify({ approval_result: { status: "completed" } }), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }

      if (url.includes("/api/v1/models/train")) {
        return new Response(JSON.stringify({ training_run: { status: "completed" } }), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }

      return new Response(JSON.stringify({ detail: `Unhandled route ${url}` }), {
        status: 404,
        headers: { "Content-Type": "application/json" }
      });
    }) as typeof fetch;
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the operator dashboard instead of the old placeholder shell", async () => {
    render(<App />);

    expect(await screen.findByText("Top Signals")).toBeInTheDocument();
    expect(screen.getByText("AAPL")).toBeInTheDocument();
    expect(screen.getByText("Pending approvals")).toBeInTheDocument();
  });

  it("saves setup changes through the config api", async () => {
    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: "Setup" }));
    const timezoneInput = await screen.findByDisplayValue("local");
    fireEvent.change(timezoneInput, { target: { value: "UTC" } });
    fireEvent.click(screen.getByRole("button", { name: "Save Setup" }));

    await screen.findByText("Configuration saved.");
    await waitFor(() => {
      expect(globalThis.fetch).toHaveBeenCalledWith(
        "/api/v1/config",
        expect.objectContaining({ method: "PUT" })
      );
    });
  });

  it("processes manual approvals from the orders screen", async () => {
    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: /Orders/i }));
    fireEvent.click(await screen.findByRole("button", { name: "Approve" }));

    await screen.findByText("Approved AAPL.");
    await waitFor(() => {
      expect(globalThis.fetch).toHaveBeenCalledWith(
        expect.stringContaining("/api/v1/live/approvals"),
        expect.objectContaining({ method: "POST" })
      );
    });
  });
});
