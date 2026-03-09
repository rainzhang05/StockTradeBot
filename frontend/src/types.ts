export type AppMode =
  | "simulation"
  | "paper"
  | "live-manual"
  | "live-autonomous"
  | "frozen";

export interface HealthCheck {
  name: string;
  ok: boolean;
  detail: string;
}

export interface HealthSnapshot {
  status: string;
  version: string;
  mode: string;
  checks: HealthCheck[];
  ui_url: string;
}

export interface SetupSnapshot {
  initialized: boolean;
  config_path: string;
  database_path: string;
}

export interface AuditEvent {
  id: number;
  category: string;
  message: string;
  created_at: string;
}

export interface ModeState {
  current_mode: AppMode;
  requested_mode: AppMode | null;
  live_profile: string;
  is_frozen: boolean;
  active_freeze_event_id: number | null;
  freeze_reason: string | null;
  metadata: Record<string, unknown>;
  updated_at: string | null;
}

export interface FreezeSnapshot {
  id: number;
  status: string;
  freeze_type: string;
  source: string;
  reason: string;
  details: Record<string, unknown>;
  triggered_at: string | null;
  cleared_at: string | null;
}

export interface PortfolioPosition {
  symbol: string;
  target_weight: number;
  actual_weight: number;
  shares: number;
  price: number;
  market_value: number;
  score: number | null;
  sector: string | null;
  metadata: Record<string, unknown>;
}

export interface TargetPortfolioSnapshot {
  id: number;
  simulation_run_id: number;
  trade_date: string;
  nav: number;
  cash_balance: number;
  gross_exposure: number;
  net_exposure: number;
  holding_count: number;
  turnover_ratio: number;
  positions: PortfolioPosition[];
}

export interface OrderSnapshot {
  id: number;
  symbol: string;
  side: string;
  status: string;
  order_type: string;
  requested_shares: number;
  requested_notional: number;
  limit_price: number | null;
  reference_price: number;
  expected_slippage_bps: number;
  target_weight: number;
  metadata: Record<string, unknown>;
  created_at: string | null;
  completed_at: string | null;
}

export interface FillSnapshot {
  id: number;
  order_intent_id: number;
  symbol: string;
  side: string;
  fill_status: string;
  filled_shares: number;
  filled_notional: number;
  fill_price: number;
  commission: number;
  slippage_bps: number;
  expected_spread_bps: number;
  metadata: Record<string, unknown>;
  filled_at: string | null;
}

export interface ApprovalSnapshot {
  approval_id: number;
  order_intent_id: number;
  broker_order_id: number | null;
  symbol: string;
  mode: string;
  status: string;
  requested_by: string | null;
  decided_by: string | null;
  reason: string | null;
  metadata: Record<string, unknown>;
  created_at: string | null;
  decided_at: string | null;
}

export interface BrokerPositionSnapshot {
  symbol: string;
  quantity: number;
  market_price: number;
  market_value: number;
  average_cost: number | null;
  unrealized_pnl: number | null;
  realized_pnl: number | null;
  currency: string;
  payload: Record<string, unknown>;
}

export interface BrokerAccountSnapshot {
  id: number;
  simulation_run_id: number | null;
  broker_name: string;
  mode: string;
  account_id: string;
  net_liquidation: number;
  cash_balance: number;
  buying_power: number;
  available_funds: number;
  cushion: number | null;
  payload: Record<string, unknown>;
  captured_at: string | null;
  positions: BrokerPositionSnapshot[];
}

export interface BrokerOrderSnapshot {
  id: number;
  simulation_run_id: number;
  order_intent_id: number | null;
  broker_name: string;
  mode: string;
  account_id: string;
  broker_order_id: string | null;
  broker_status: string;
  approval_status: string;
  symbol: string;
  side: string;
  order_type: string;
  time_in_force: string;
  requested_shares: number;
  filled_shares: number;
  limit_price: number | null;
  average_fill_price: number | null;
  preview_commission: number | null;
  warnings: string[];
  payload: Record<string, unknown>;
  created_at: string | null;
  updated_at: string | null;
}

export interface SimulationRunSnapshot {
  id: number;
  status: string;
  mode: string;
  as_of_date: string | null;
  decision_date: string | null;
  model_entry_id: number | null;
  dataset_snapshot_id: number | null;
  regime: string | null;
  gross_exposure_target: number;
  gross_exposure_actual: number;
  start_nav: number;
  end_nav: number;
  cash_start: number;
  cash_end: number;
  artifact_path: string | null;
  summary: Record<string, unknown>;
  error_message: string | null;
  created_at: string | null;
  completed_at: string | null;
}

export interface SimulationStatusSnapshot {
  mode_state: ModeState | null;
  active_freeze: FreezeSnapshot | null;
  latest_run: SimulationRunSnapshot | null;
  latest_target_snapshot: TargetPortfolioSnapshot | null;
}

export interface BrokerConnectivity {
  ok: boolean;
  detail: string;
  environment?: string;
  account_id?: string;
}

export interface BrokerConnectionStatus {
  configured: boolean;
  provider: string;
  message: string;
  paper_account_id: string | null;
  live_account_id: string | null;
  gateway: Record<string, unknown>;
  connectivity: BrokerConnectivity | null;
  accounts: string[];
  gates?: Record<string, unknown>;
  config?: Record<string, unknown>;
}

export interface PaperStatus {
  mode_state: ModeState | null;
  latest_run: SimulationRunSnapshot | null;
  broker: BrokerConnectionStatus;
  paper_safe_days: number;
  active_freeze: FreezeSnapshot | null;
}

export interface LiveGateCheck {
  name: string;
  ok: boolean;
  detail: string;
}

export interface LiveStatus {
  mode_state: ModeState | null;
  latest_run: SimulationRunSnapshot | null;
  latest_approvals: ApprovalSnapshot[];
  broker: BrokerConnectionStatus;
  gates: {
    manual: { allowed: boolean; checks: LiveGateCheck[] };
    autonomous: { allowed: boolean; checks: LiveGateCheck[] };
  };
  safe_day_counts: {
    paper: number;
    paper_and_live: number;
  };
  active_freeze: FreezeSnapshot | null;
}

export interface MarketDataStatus {
  latest_run: {
    id: number;
    status: string;
    as_of_date: string;
    primary_provider: string;
    secondary_provider: string | null;
    summary: Record<string, unknown>;
    completed_at: string | null;
  } | null;
  latest_universe_snapshot: {
    id: number;
    effective_date: string;
    stock_count: number;
    etf_count: number;
    selection_version: string;
    summary: Record<string, unknown>;
  } | null;
  validation_counts: Record<string, number>;
  fundamentals_observation_count: number;
  recent_incidents: Array<{
    id: number;
    symbol: string;
    trade_date: string;
    domain: string;
    affected_fields: string[];
    involved_providers: string[];
    observed_values: Record<string, unknown>;
    resolution_status: string;
    operator_notes: string | null;
    created_at: string;
    resolved_at: string | null;
  }>;
}

export interface DatasetStatus {
  latest_dataset_snapshot: {
    id: number;
    as_of_date: string;
    universe_snapshot_id: number | null;
    feature_set_version: string;
    label_version: string;
    row_count: number;
    artifact_path: string;
    null_statistics: Record<string, number>;
    metadata: Record<string, unknown>;
    created_at: string;
  } | null;
  feature_set_versions: Array<{
    version: string;
    definition: Record<string, unknown>;
    created_at: string;
  }>;
  label_versions: Array<{
    version: string;
    definition: Record<string, unknown>;
    created_at: string;
  }>;
  fundamentals_observation_count: number;
}

export interface ModelStatus {
  latest_training_run: {
    id: number;
    status: string;
    as_of_date: string | null;
    dataset_snapshot_id: number | null;
    model_family: string;
    model_version: string | null;
    summary: Record<string, unknown>;
    error_message: string | null;
    created_at: string | null;
    completed_at: string | null;
  } | null;
  latest_model: {
    id: number;
    version: string;
    family: string;
    dataset_snapshot_id: number;
    feature_set_version: string;
    label_version: string;
    training_start_date: string;
    training_end_date: string;
    training_row_count: number;
    artifact_path: string;
    metrics: Record<string, number>;
    benchmark_metrics: Record<string, number>;
    promotion_status: string;
    promotion_reasons: string[];
    created_at: string | null;
  } | null;
  latest_validation_run: {
    id: number;
    status: string;
    dataset_snapshot_id: number;
    model_entry_id: number | null;
    fold_count: number;
    artifact_path: string | null;
    summary: Record<string, unknown>;
    error_message: string | null;
    created_at: string | null;
    completed_at: string | null;
  } | null;
  latest_backtest_run: {
    id: number;
    status: string;
    mode: string;
    dataset_snapshot_id: number;
    model_entry_id: number | null;
    benchmark_symbol: string;
    start_date: string;
    end_date: string;
    artifact_path: string | null;
    summary: Record<string, unknown>;
    error_message: string | null;
    created_at: string | null;
    completed_at: string | null;
  } | null;
}

export interface WorkspaceSnapshot {
  health: HealthSnapshot;
  setup: SetupSnapshot;
  config: Record<string, unknown>;
  system: {
    status: Record<string, unknown>;
    audit_events: AuditEvent[];
  };
  broker: {
    paper: PaperStatus;
    live: LiveStatus;
  };
  market_data: MarketDataStatus;
  datasets: DatasetStatus;
  models: ModelStatus;
  risk: {
    mode_state: ModeState | null;
    active_freeze: FreezeSnapshot | null;
  };
  portfolio: {
    status: SimulationStatusSnapshot;
    latest_target_snapshot: TargetPortfolioSnapshot | null;
    latest_orders: OrderSnapshot[];
    latest_fills: FillSnapshot[];
  };
  paper: PaperStatus;
  live: LiveStatus;
}
