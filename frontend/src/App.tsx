import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import {
  ApiError,
  approveLive,
  backfillMarketData,
  backtestModel,
  fetchWorkspace,
  runLive,
  runPaper,
  runSimulation,
  trainModel,
  updateConfig,
  updateMode
} from "./api";
import type {
  ApprovalSnapshot,
  AuditEvent,
  FillSnapshot,
  HealthCheck,
  LiveGateCheck,
  OperationalLogEvent,
  OrderSnapshot,
  PortfolioPosition,
  WorkspaceSnapshot
} from "./types";

type ScreenKey = "overview" | "stocks" | "activity" | "setup";
type Tone = "default" | "success" | "attention" | "danger" | "muted";

interface SetupDraft {
  timezone: string;
  databasePath: string;
  artifactsDir: string;
  logsDir: string;
  primaryProvider: string;
  secondaryProvider: string;
  alphaEnabled: boolean;
  fundamentalsEnabled: boolean;
  fundamentalsUserAgent: string;
  stockCandidates: string;
  curatedEtfs: string;
  brokerEnabled: boolean;
  operatorName: string;
  paperAccountId: string;
  liveAccountId: string;
  gatewayBaseUrl: string;
  defaultMode: string;
  liveProfile: string;
  dailyLossCap: string;
  drawdownFreeze: string;
}

interface StockRow {
  symbol: string;
  score: number | null;
  targetWeight: number | null;
  price: number | null;
  marketValue: number | null;
  status: string;
  tone: Tone;
  approvalStatus: string;
  approval: ApprovalSnapshot | null;
  latestAction: string;
}

interface ActivityItem {
  id: string;
  title: string;
  note: string;
  timestamp: string | null;
  tone: Tone;
}

const screens: Array<{ key: ScreenKey; label: string }> = [
  { key: "overview", label: "Overview" },
  { key: "stocks", label: "Stocks" },
  { key: "activity", label: "Activity" },
  { key: "setup", label: "Setup" }
];

const highlightedChecks = [
  { name: "database-connectivity", label: "Database" },
  { name: "primary-provider", label: "Market data" },
  { name: "fundamentals-provider", label: "Fundamentals" },
  { name: "broker-connectivity", label: "Broker" }
];

function readHashScreen(): ScreenKey {
  const hash = window.location.hash.replace("#", "");
  return screens.some((screen) => screen.key === hash) ? (hash as ScreenKey) : "overview";
}

function writeHashScreen(screen: ScreenKey): void {
  window.location.hash = screen;
}

function formatCurrency(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined) {
    return "n/a";
  }
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: digits,
    minimumFractionDigits: digits
  }).format(value);
}

function formatPercent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined) {
    return "n/a";
  }
  return `${(value * 100).toFixed(digits)}%`;
}

function formatNumber(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined) {
    return "n/a";
  }
  return value.toFixed(digits);
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) {
    return "n/a";
  }
  return new Date(value).toLocaleString();
}

function parseSymbolList(value: string): string[] {
  return value
    .split(/[\s,]+/)
    .map((item) => item.trim().toUpperCase())
    .filter(Boolean);
}

function emptyToNull(value: string): string | null {
  const trimmed = value.trim();
  return trimmed.length === 0 ? null : trimmed;
}

function messageFromError(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "Unexpected error.";
}

function toTitleCase(value: string | null | undefined): string {
  if (!value) {
    return "n/a";
  }
  return value
    .replace(/[-_]/g, " ")
    .replace(/\b\w/g, (match) => match.toUpperCase());
}

function summaryNumber(summary: Record<string, unknown> | null | undefined, key: string): number | null {
  const value = summary?.[key];
  return typeof value === "number" ? value : null;
}

function valueTone(value: number | null | undefined): Tone {
  if (value === null || value === undefined) {
    return "muted";
  }
  if (value > 0) {
    return "success";
  }
  if (value < 0) {
    return "danger";
  }
  return "default";
}

function statusTone(ok: boolean): Tone {
  return ok ? "success" : "attention";
}

function modeTone(mode: string | null | undefined): Tone {
  if (!mode) {
    return "muted";
  }
  if (mode === "simulation") {
    return "default";
  }
  if (mode === "paper") {
    return "attention";
  }
  if (mode === "frozen") {
    return "danger";
  }
  return "danger";
}

function healthTone(workspace: WorkspaceSnapshot | null): Tone {
  if (!workspace) {
    return "muted";
  }
  if (workspace.risk.active_freeze) {
    return "danger";
  }
  return workspace.health.status === "ok" ? "success" : "attention";
}

function healthLabel(workspace: WorkspaceSnapshot | null): string {
  if (!workspace) {
    return "Loading";
  }
  if (workspace.risk.active_freeze) {
    return "Frozen";
  }
  return workspace.health.status === "ok" ? "Ready" : "Needs attention";
}

function currentModeLabel(workspace: WorkspaceSnapshot | null): string {
  return toTitleCase(workspace?.risk.mode_state?.current_mode ?? "simulation");
}

function headlineForWorkspace(workspace: WorkspaceSnapshot | null): string {
  if (!workspace) {
    return "Loading your trading workspace.";
  }
  if (workspace.risk.active_freeze) {
    return "Trading is paused until the active freeze is cleared.";
  }
  if (workspace.health.status !== "ok") {
    return "A few setup items still need attention before trading.";
  }
  return `${currentModeLabel(workspace)} mode is ready.`;
}

function copyForWorkspace(workspace: WorkspaceSnapshot | null): string {
  if (!workspace) {
    return "Checking local services and loading the latest status.";
  }
  if (workspace.risk.active_freeze) {
    return workspace.risk.active_freeze.reason;
  }
  const pendingApprovals =
    workspace.live.latest_approvals.filter((approval) => approval.status === "pending").length;
  if (pendingApprovals > 0) {
    return `${pendingApprovals} order${pendingApprovals === 1 ? "" : "s"} still need approval before they can be sent live.`;
  }
  return "The dashboard is showing only the key status, performance, and stock-level actions needed to operate the system.";
}

function configuredUniverse(config: Record<string, any> | null): string[] {
  const universe = (config?.universe ?? {}) as Record<string, any>;
  return [
    ...((universe.stock_candidates ?? []) as string[]),
    ...((universe.curated_etfs ?? []) as string[])
  ];
}

function initialSetupDraft(config: Record<string, any> | null): SetupDraft {
  const dataProviders = (config?.data_providers ?? {}) as Record<string, any>;
  const alpha = (dataProviders.alpha_vantage ?? {}) as Record<string, any>;
  const fundamentals = (config?.fundamentals_provider ?? {}) as Record<string, any>;
  const universe = (config?.universe ?? {}) as Record<string, any>;
  const broker = (config?.broker ?? {}) as Record<string, any>;
  const gateway = (broker.gateway ?? {}) as Record<string, any>;
  const execution = (config?.execution ?? {}) as Record<string, any>;
  const risk = (config?.risk ?? {}) as Record<string, any>;

  return {
    timezone: String(config?.timezone ?? "local"),
    databasePath: String(config?.database_path ?? ""),
    artifactsDir: String(config?.artifacts_dir ?? ""),
    logsDir: String(config?.logs_dir ?? ""),
    primaryProvider: String(dataProviders.primary_provider ?? "stooq"),
    secondaryProvider: String(dataProviders.secondary_provider ?? ""),
    alphaEnabled: Boolean(alpha.enabled),
    fundamentalsEnabled: Boolean(fundamentals.enabled),
    fundamentalsUserAgent: String(fundamentals.user_agent ?? ""),
    stockCandidates: ((universe.stock_candidates ?? []) as string[]).join(", "),
    curatedEtfs: ((universe.curated_etfs ?? []) as string[]).join(", "),
    brokerEnabled: Boolean(broker.enabled),
    operatorName: String(broker.operator_name ?? "local-operator"),
    paperAccountId: String(broker.paper_account_id ?? ""),
    liveAccountId: String(broker.live_account_id ?? ""),
    gatewayBaseUrl: String(gateway.base_url ?? "https://127.0.0.1:5000/v1/api"),
    defaultMode: String(execution.default_mode ?? "simulation"),
    liveProfile: String(execution.live_profile ?? "manual"),
    dailyLossCap: String(risk.daily_loss_cap ?? 0.03),
    drawdownFreeze: String(risk.drawdown_freeze ?? 0.2)
  };
}

function buildActivityFeed(workspace: WorkspaceSnapshot | null): ActivityItem[] {
  if (!workspace) {
    return [];
  }

  const auditItems = workspace.system.audit_events.map((item: AuditEvent) => ({
    id: `audit-${item.id}`,
    title: item.message,
    note: toTitleCase(item.category),
    timestamp: item.created_at,
    tone: "default" as Tone
  }));

  const logItems = workspace.system.logs.map((item: OperationalLogEvent, index) => ({
    id: `log-${item.timestamp ?? "missing"}-${index}`,
    title: item.message,
    note: toTitleCase(item.category),
    timestamp: item.timestamp,
    tone:
      item.level === "error" ? "danger" : item.level === "warning" ? "attention" : ("muted" as Tone)
  }));

  return [...auditItems, ...logItems]
    .sort((left, right) => {
      const leftTime = left.timestamp ? Date.parse(left.timestamp) : 0;
      const rightTime = right.timestamp ? Date.parse(right.timestamp) : 0;
      return rightTime - leftTime;
    })
    .slice(0, 8);
}

function buildStockRows(workspace: WorkspaceSnapshot | null): StockRow[] {
  if (!workspace) {
    return [];
  }

  const positionsBySymbol = new Map<string, PortfolioPosition>();
  for (const position of workspace.portfolio.latest_target_snapshot?.positions ?? []) {
    positionsBySymbol.set(position.symbol, position);
  }

  const ordersBySymbol = new Map<string, OrderSnapshot>();
  for (const order of workspace.portfolio.latest_orders ?? []) {
    if (!ordersBySymbol.has(order.symbol)) {
      ordersBySymbol.set(order.symbol, order);
    }
  }

  const fillsBySymbol = new Map<string, FillSnapshot>();
  for (const fill of workspace.portfolio.latest_fills ?? []) {
    if (!fillsBySymbol.has(fill.symbol)) {
      fillsBySymbol.set(fill.symbol, fill);
    }
  }

  const approvalsBySymbol = new Map<string, ApprovalSnapshot>();
  for (const approval of workspace.live.latest_approvals ?? []) {
    if (!approvalsBySymbol.has(approval.symbol)) {
      approvalsBySymbol.set(approval.symbol, approval);
    }
  }

  const symbols = new Set<string>([
    ...positionsBySymbol.keys(),
    ...ordersBySymbol.keys(),
    ...fillsBySymbol.keys(),
    ...approvalsBySymbol.keys()
  ]);

  return [...symbols]
    .map((symbol) => {
      const position = positionsBySymbol.get(symbol) ?? null;
      const order = ordersBySymbol.get(symbol) ?? null;
      const fill = fillsBySymbol.get(symbol) ?? null;
      const approval = approvalsBySymbol.get(symbol) ?? null;

      let status = "Watching";
      let tone: Tone = "muted";

      if (workspace.risk.active_freeze) {
        status = "Paused";
        tone = "danger";
      } else if (approval?.status === "pending") {
        status = "Awaiting approval";
        tone = "attention";
      } else if (fill !== null) {
        status = toTitleCase(fill.fill_status);
        tone = fill.fill_status === "filled" ? "success" : "attention";
      } else if (order !== null) {
        status = toTitleCase(order.status);
        tone = order.status === "submitted" ? "attention" : "default";
      } else if ((position?.target_weight ?? 0) > 0) {
        status = "Ready";
        tone = "success";
      }

      const latestAction = fill?.filled_at ?? order?.created_at ?? approval?.created_at ?? null;
      return {
        symbol,
        score: position?.score ?? null,
        targetWeight: position?.target_weight ?? null,
        price: position?.price ?? order?.reference_price ?? fill?.fill_price ?? null,
        marketValue: position?.market_value ?? fill?.filled_notional ?? order?.requested_notional ?? null,
        status,
        tone,
        approvalStatus: approval ? toTitleCase(approval.status) : "Not needed",
        approval,
        latestAction: latestAction ? formatDateTime(latestAction) : "No recent activity"
      };
    })
    .sort((left, right) => {
      const leftScore = left.score ?? -999;
      const rightScore = right.score ?? -999;
      if (leftScore !== rightScore) {
        return rightScore - leftScore;
      }
      return left.symbol.localeCompare(right.symbol);
    });
}

function statusSummaryRows(workspace: WorkspaceSnapshot | null): Array<{ label: string; value: string; tone: Tone }> {
  if (!workspace) {
    return [];
  }

  const checksByName = new Map(workspace.health.checks.map((check) => [check.name, check]));
  return highlightedChecks.map((item) => {
    const check = checksByName.get(item.name);
    return {
      label: item.label,
      value: check?.detail ?? "Not available",
      tone: check ? statusTone(check.ok) : "muted"
    };
  });
}

function Badge(props: { label: string; tone?: Tone }): JSX.Element {
  return <span className={`badge badge--${props.tone ?? "default"}`}>{props.label}</span>;
}

function SectionCard(props: {
  title: string;
  description?: string;
  actions?: ReactNode;
  children: ReactNode;
}): JSX.Element {
  return (
    <section className="card section-card">
      <div className="section-card__header">
        <div>
          <p className="eyebrow">{props.title}</p>
          {props.description ? <p className="section-card__description">{props.description}</p> : null}
        </div>
        {props.actions ? <div className="section-card__actions">{props.actions}</div> : null}
      </div>
      {props.children}
    </section>
  );
}

function StatCard(props: {
  label: string;
  value: string;
  detail?: string;
  tone?: Tone;
}): JSX.Element {
  return (
    <article className={`stat-card stat-card--${props.tone ?? "default"}`}>
      <p className="stat-card__label">{props.label}</p>
      <p className="stat-card__value">{props.value}</p>
      {props.detail ? <p className="stat-card__detail">{props.detail}</p> : null}
    </article>
  );
}

function Table(props: {
  columns: string[];
  rows: ReactNode[][];
  emptyMessage: string;
}): JSX.Element {
  if (props.rows.length === 0) {
    return <p className="empty-state">{props.emptyMessage}</p>;
  }

  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            {props.columns.map((column) => (
              <th key={column}>{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {props.rows.map((row, rowIndex) => (
            <tr key={`${props.columns[0]}-${rowIndex}`}>
              {row.map((cell, cellIndex) => (
                <td key={`${rowIndex}-${cellIndex}`}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function HealthList(props: { items: Array<{ label: string; value: string; tone: Tone }> }): JSX.Element {
  return (
    <div className="health-list">
      {props.items.map((item) => (
        <article className="health-list__item" key={item.label}>
          <div>
            <p className="health-list__label">{item.label}</p>
            <p className="health-list__value">{item.value}</p>
          </div>
          <Badge label={item.tone === "success" ? "Ready" : item.tone === "attention" ? "Check" : "Info"} tone={item.tone} />
        </article>
      ))}
    </div>
  );
}

function ActivityFeed(props: { items: ActivityItem[] }): JSX.Element {
  if (props.items.length === 0) {
    return <p className="empty-state">No recent activity yet.</p>;
  }

  return (
    <div className="activity-list">
      {props.items.map((item) => (
        <article className="activity-list__item" key={item.id}>
          <div className="activity-list__copy">
            <p className="activity-list__title">{item.title}</p>
            <p className="activity-list__note">{item.note}</p>
          </div>
          <div className="activity-list__meta">
            <Badge label={item.tone === "danger" ? "Alert" : item.tone === "attention" ? "Watch" : "Recent"} tone={item.tone} />
            <span>{formatDateTime(item.timestamp)}</span>
          </div>
        </article>
      ))}
    </div>
  );
}

function SetupStepList(props: { items: Array<{ label: string; ok: boolean }> }): JSX.Element {
  return (
    <div className="setup-steps">
      {props.items.map((item) => (
        <article className="setup-steps__item" key={item.label}>
          <div className={`setup-steps__dot ${item.ok ? "setup-steps__dot--ready" : ""}`} />
          <p>{item.label}</p>
          <Badge label={item.ok ? "Done" : "Next"} tone={item.ok ? "success" : "attention"} />
        </article>
      ))}
    </div>
  );
}

function App(): JSX.Element {
  const [activeScreen, setActiveScreen] = useState<ScreenKey>(readHashScreen);
  const [workspace, setWorkspace] = useState<WorkspaceSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [activeAction, setActiveAction] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  const [setupDraft, setSetupDraft] = useState<SetupDraft>(() => initialSetupDraft(null));
  const [setupDirty, setSetupDirty] = useState(false);
  const [ackDisableApprovals, setAckDisableApprovals] = useState(false);

  const config = (workspace?.config ?? null) as Record<string, any> | null;
  const stockRows = buildStockRows(workspace);
  const activityItems = buildActivityFeed(workspace);
  const readinessRows = statusSummaryRows(workspace);
  const pendingApprovals =
    workspace?.live.latest_approvals.filter((approval) => approval.status === "pending") ?? [];
  const backtestSummary = (workspace?.models.latest_backtest_run?.summary ?? {}) as Record<
    string,
    unknown
  >;
  const latestRunProfit =
    workspace?.portfolio.status.latest_run !== null && workspace?.portfolio.status.latest_run !== undefined
      ? (workspace.portfolio.status.latest_run.end_nav ?? 0) -
        (workspace.portfolio.status.latest_run.start_nav ?? 0)
      : null;
  const backtestReturn =
    summaryNumber(backtestSummary, "total_return") ??
    workspace?.models.latest_model?.metrics["total_return"] ??
    null;
  const benchmarkReturn =
    summaryNumber(backtestSummary, "benchmark_return") ??
    workspace?.models.latest_model?.benchmark_metrics["benchmark_return"] ??
    null;
  const backtestExcess =
    summaryNumber(backtestSummary, "excess_return") ??
    (backtestReturn !== null && benchmarkReturn !== null ? backtestReturn - benchmarkReturn : null);
  const latestNav = workspace?.portfolio.latest_target_snapshot?.nav ?? null;
  const latestCash = workspace?.portfolio.latest_target_snapshot?.cash_balance ?? null;
  const trackedSymbols = stockRows.length;
  const highlightedStocks = stockRows.slice(0, 6);

  async function loadWorkspace(background = false): Promise<void> {
    if (background) {
      setRefreshing(true);
    } else {
      setLoading(true);
      setLoadError(null);
    }

    try {
      const snapshot = await fetchWorkspace();
      setWorkspace(snapshot);
      setLastUpdated(new Date().toISOString());
      setLoadError(null);
    } catch (error) {
      setLoadError(messageFromError(error));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }

  useEffect(() => {
    void loadWorkspace(false);
    const intervalId = window.setInterval(() => {
      void loadWorkspace(true);
    }, 15000);
    return () => window.clearInterval(intervalId);
  }, []);

  useEffect(() => {
    const onHashChange = (): void => setActiveScreen(readHashScreen());
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  useEffect(() => {
    if (!workspace || setupDirty) {
      return;
    }
    setSetupDraft(initialSetupDraft(workspace.config as Record<string, any>));
  }, [workspace, setupDirty]);

  function selectScreen(screen: ScreenKey): void {
    setActiveScreen(screen);
    writeHashScreen(screen);
  }

  async function runAction(
    actionName: string,
    task: () => Promise<unknown>,
    successMessage: string,
  ): Promise<void> {
    setActiveAction(actionName);
    setActionMessage(null);
    setActionError(null);
    try {
      await task();
      setActionMessage(successMessage);
      await loadWorkspace(true);
    } catch (error) {
      setActionError(messageFromError(error));
    } finally {
      setActiveAction(null);
    }
  }

  function updateDraft<K extends keyof SetupDraft>(key: K, value: SetupDraft[K]): void {
    setSetupDirty(true);
    setSetupDraft((current) => ({ ...current, [key]: value }));
  }

  async function saveSetup(): Promise<void> {
    const patch = {
      timezone: setupDraft.timezone,
      database_path: setupDraft.databasePath,
      artifacts_dir: setupDraft.artifactsDir,
      logs_dir: setupDraft.logsDir,
      data_providers: {
        primary_provider: setupDraft.primaryProvider,
        secondary_provider: emptyToNull(setupDraft.secondaryProvider),
        alpha_vantage: {
          enabled: setupDraft.alphaEnabled
        }
      },
      fundamentals_provider: {
        enabled: setupDraft.fundamentalsEnabled,
        user_agent: emptyToNull(setupDraft.fundamentalsUserAgent)
      },
      universe: {
        stock_candidates: parseSymbolList(setupDraft.stockCandidates),
        curated_etfs: parseSymbolList(setupDraft.curatedEtfs)
      },
      broker: {
        enabled: setupDraft.brokerEnabled,
        operator_name: setupDraft.operatorName,
        paper_account_id: emptyToNull(setupDraft.paperAccountId),
        live_account_id: emptyToNull(setupDraft.liveAccountId),
        gateway: {
          base_url: setupDraft.gatewayBaseUrl
        }
      },
      execution: {
        default_mode: setupDraft.defaultMode,
        live_profile: setupDraft.liveProfile
      },
      risk: {
        daily_loss_cap: Number(setupDraft.dailyLossCap),
        drawdown_freeze: Number(setupDraft.drawdownFreeze)
      }
    };

    await runAction("save-setup", () => updateConfig(patch), "Setup saved.");
    setSetupDirty(false);
  }

  async function approveSingle(symbol: string): Promise<void> {
    await runAction(
      `approve-${symbol}`,
      () =>
        approveLive({
          runId: workspace?.live.latest_run?.id,
          approveSymbols: [symbol]
        }),
      `Approved ${symbol}.`,
    );
  }

  async function rejectSingle(symbol: string): Promise<void> {
    await runAction(
      `reject-${symbol}`,
      () =>
        approveLive({
          runId: workspace?.live.latest_run?.id,
          rejectSymbols: [symbol]
        }),
      `Rejected ${symbol}.`,
    );
  }

  const setupSteps = [
    {
      label: "Choose where the app stores its local files",
      ok: workspace?.setup.initialized ?? false
    },
    {
      label: "Connect a market data source",
      ok: workspace?.health.checks.some((check) => check.name === "primary-provider" && check.ok) ?? false
    },
    {
      label: "Enable fundamentals when the SEC user agent is ready",
      ok: workspace?.health.checks.some((check) => check.name === "fundamentals-provider" && check.ok) ?? false
    },
    {
      label: "Save broker accounts if you plan to use paper or live trading",
      ok: Boolean(config?.broker?.paper_account_id) && Boolean(config?.broker?.live_account_id)
    },
    {
      label: "Run readiness checks until the system is green",
      ok: workspace?.health.status === "ok"
    },
    {
      label: "Stay in simulation mode until paper trading is ready",
      ok: workspace?.risk.mode_state?.current_mode === "simulation"
    }
  ];

  const modeButtons = [
    { key: "simulation", label: "Simulation" },
    { key: "paper", label: "Paper" },
    { key: "live-manual", label: "Live Manual" },
    { key: "live-autonomous", label: "Live Auto" }
  ];

  if (loading && workspace === null) {
    return (
      <main className="shell">
        <section className="hero card">
          <div className="hero__copy">
            <p className="eyebrow">StockTradeBot</p>
            <h1>Loading your workspace</h1>
            <p className="hero__description">Checking the local runtime, database, and latest market state.</p>
          </div>
        </section>
      </main>
    );
  }

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">StockTradeBot</p>
          <h1>{headlineForWorkspace(workspace)}</h1>
          <p className="topbar__copy">{copyForWorkspace(workspace)}</p>
        </div>
        <div className="topbar__meta">
          <Badge label={healthLabel(workspace)} tone={healthTone(workspace)} />
          <Badge label={currentModeLabel(workspace)} tone={modeTone(workspace?.risk.mode_state?.current_mode)} />
          <button
            type="button"
            className="button button--secondary"
            disabled={refreshing}
            onClick={() => void loadWorkspace(true)}
          >
            {refreshing ? "Refreshing..." : "Refresh"}
          </button>
          <p className="topbar__timestamp">
            Last updated {lastUpdated ? formatDateTime(lastUpdated) : "n/a"}
          </p>
        </div>
      </header>

      {loadError ? <p className="banner banner--danger">{loadError}</p> : null}
      {actionError ? <p className="banner banner--danger">{actionError}</p> : null}
      {actionMessage ? <p className="banner banner--success">{actionMessage}</p> : null}

      <nav className="tabs" aria-label="Main views">
        {screens.map((screen) => (
          <button
            type="button"
            key={screen.key}
            className={screen.key === activeScreen ? "tabs__item tabs__item--active" : "tabs__item"}
            onClick={() => selectScreen(screen.key)}
          >
            {screen.label}
            {screen.key === "stocks" && pendingApprovals.length > 0 ? (
              <span className="tabs__count">{pendingApprovals.length}</span>
            ) : null}
          </button>
        ))}
      </nav>

      {activeScreen === "overview" ? (
        <div className="screen-grid">
          <section className="hero card">
            <div className="hero__copy">
              <p className="eyebrow">Current state</p>
              <h2>{headlineForWorkspace(workspace)}</h2>
              <p className="hero__description">{copyForWorkspace(workspace)}</p>
              <div className="hero__badges">
                <Badge label={workspace?.risk.active_freeze ? "Freeze active" : "No freeze"} tone={workspace?.risk.active_freeze ? "danger" : "success"} />
                <Badge label={`${pendingApprovals.length} pending approval${pendingApprovals.length === 1 ? "" : "s"}`} tone={pendingApprovals.length > 0 ? "attention" : "muted"} />
                <Badge label={`${trackedSymbols} tracked stocks`} tone="muted" />
              </div>
            </div>
            <div className="hero__stats">
              <StatCard
                label="Backtest profit"
                value={formatPercent(backtestReturn)}
                detail={
                  benchmarkReturn !== null
                    ? `Benchmark ${formatPercent(benchmarkReturn)}`
                    : "Run a backtest to compare against SPY."
                }
                tone={valueTone(backtestReturn)}
              />
              <StatCard
                label="Profit after latest run"
                value={formatCurrency(latestRunProfit)}
                detail={
                  workspace?.portfolio.status.latest_run?.completed_at
                    ? formatDateTime(workspace.portfolio.status.latest_run.completed_at)
                    : "No completed run yet."
                }
                tone={valueTone(latestRunProfit)}
              />
              <StatCard
                label="Portfolio value"
                value={formatCurrency(latestNav)}
                detail={latestCash !== null ? `Cash ${formatCurrency(latestCash)}` : "No portfolio snapshot yet."}
                tone="default"
              />
            </div>
          </section>

          <SectionCard
            title="Change mode"
            description="Switch the system mode without leaving the main screen."
            actions={
              <label className="toggle">
                <input
                  type="checkbox"
                  checked={ackDisableApprovals}
                  onChange={(event) => setAckDisableApprovals(event.target.checked)}
                />
                <span>I understand live auto skips order approvals</span>
              </label>
            }
          >
            <div className="button-row">
              {modeButtons.map((item) => (
                <button
                  type="button"
                  key={item.key}
                  className={
                    item.key === "live-autonomous"
                      ? "button button--danger"
                      : "button button--secondary"
                  }
                  disabled={activeAction === `mode-${item.key}`}
                  onClick={() =>
                    void runAction(
                      `mode-${item.key}`,
                      () => updateMode(item.key, ackDisableApprovals),
                      `${item.label} selected.`,
                    )
                  }
                >
                  {activeAction === `mode-${item.key}` ? "Updating..." : item.label}
                </button>
              ))}
            </div>
          </SectionCard>

          <SectionCard title="Quick actions" description="Run the main tasks without exposing raw backend details.">
            <div className="button-grid">
              <button
                type="button"
                className="button"
                disabled={activeAction === "backfill"}
                onClick={() =>
                  void runAction(
                    "backfill",
                    () =>
                      backfillMarketData({
                        lookbackDays: 180,
                        symbols: configuredUniverse(config)
                      }),
                    "Market data refreshed.",
                  )
                }
              >
                {activeAction === "backfill" ? "Refreshing data..." : "Refresh data"}
              </button>
              <button
                type="button"
                className="button"
                disabled={activeAction === "train-model"}
                onClick={() => void runAction("train-model", () => trainModel(), "Model training completed.")}
              >
                {activeAction === "train-model" ? "Training..." : "Train model"}
              </button>
              <button
                type="button"
                className="button"
                disabled={activeAction === "backtest-model"}
                onClick={() => void runAction("backtest-model", () => backtestModel(), "Backtest completed.")}
              >
                {activeAction === "backtest-model" ? "Running backtest..." : "Run backtest"}
              </button>
              <button
                type="button"
                className="button button--secondary"
                disabled={activeAction === "simulate-run"}
                onClick={() =>
                  void runAction("simulate-run", () => runSimulation({}), "Simulation completed.")
                }
              >
                {activeAction === "simulate-run" ? "Running simulation..." : "Run simulation"}
              </button>
              <button
                type="button"
                className="button button--secondary"
                disabled={activeAction === "paper-run"}
                onClick={() => void runAction("paper-run", () => runPaper({}), "Paper trading completed.")}
              >
                {activeAction === "paper-run" ? "Running paper..." : "Run paper"}
              </button>
              <button
                type="button"
                className="button button--secondary"
                disabled={activeAction === "live-run"}
                onClick={() =>
                  void runAction(
                    "live-run",
                    () => runLive({ ackDisableApprovals }),
                    "Live workflow submitted.",
                  )
                }
              >
                {activeAction === "live-run" ? "Preparing live..." : "Prepare live"}
              </button>
            </div>
          </SectionCard>

          <SectionCard title="System readiness" description="A short checklist of the essentials.">
            <HealthList items={readinessRows} />
          </SectionCard>

          <SectionCard title="Stocks that need attention" description="The highest-priority symbols from the current target portfolio and order queue.">
            <Table
              columns={["Stock", "Score", "Target", "Price", "Status", "Approval"]}
              rows={highlightedStocks.map((row) => [
                <strong key={`${row.symbol}-symbol`}>{row.symbol}</strong>,
                formatNumber(row.score, 3),
                formatPercent(row.targetWeight),
                formatCurrency(row.price, 2),
                <Badge key={`${row.symbol}-status`} label={row.status} tone={row.tone} />,
                row.approvalStatus
              ])}
              emptyMessage="No stocks are ready yet."
            />
          </SectionCard>

          <SectionCard title="Recent activity" description="Latest events from the system and audit trail.">
            <ActivityFeed items={activityItems} />
          </SectionCard>
        </div>
      ) : null}

      {activeScreen === "stocks" ? (
        <div className="screen-grid">
          <SectionCard title="Stock status" description="Each stock is shown with its latest signal, target, and order state.">
            <Table
              columns={["Stock", "Score", "Target", "Price", "Value", "Current status", "Last update", "Actions"]}
              rows={stockRows.map((row) => [
                <strong key={`${row.symbol}-stock`}>{row.symbol}</strong>,
                formatNumber(row.score, 3),
                formatPercent(row.targetWeight),
                formatCurrency(row.price, 2),
                formatCurrency(row.marketValue),
                <Badge key={`${row.symbol}-badge`} label={row.status} tone={row.tone} />,
                row.latestAction,
                row.approval?.status === "pending" ? (
                  <div className="row-actions">
                    <button
                      type="button"
                      className="button button--small"
                      disabled={activeAction === `approve-${row.symbol}`}
                      onClick={() => void approveSingle(row.symbol)}
                    >
                      Approve
                    </button>
                    <button
                      type="button"
                      className="button button--small button--secondary"
                      disabled={activeAction === `reject-${row.symbol}`}
                      onClick={() => void rejectSingle(row.symbol)}
                    >
                      Reject
                    </button>
                  </div>
                ) : (
                  "No action needed"
                )
              ])}
              emptyMessage="No stock activity has been recorded yet."
            />
          </SectionCard>

          <SectionCard title="Portfolio snapshot" description="A simple summary of the current target portfolio.">
            <div className="stats-grid">
              <StatCard
                label="Holdings"
                value={String(workspace?.portfolio.latest_target_snapshot?.holding_count ?? 0)}
                detail={workspace?.portfolio.latest_target_snapshot?.trade_date ?? "No trade date yet."}
              />
              <StatCard
                label="Gross exposure"
                value={formatPercent(workspace?.portfolio.latest_target_snapshot?.gross_exposure)}
                detail={`Net ${formatPercent(workspace?.portfolio.latest_target_snapshot?.net_exposure)}`}
              />
              <StatCard
                label="Turnover"
                value={formatPercent(workspace?.portfolio.latest_target_snapshot?.turnover_ratio)}
                detail="Latest target portfolio snapshot"
              />
            </div>
          </SectionCard>
        </div>
      ) : null}

      {activeScreen === "activity" ? (
        <div className="screen-grid">
          <SectionCard title="Performance" description="Backtest results and the latest trading run at a glance.">
            <div className="stats-grid">
              <StatCard
                label="Backtest return"
                value={formatPercent(backtestReturn)}
                detail={workspace?.models.latest_backtest_run?.completed_at ? formatDateTime(workspace.models.latest_backtest_run.completed_at) : "No backtest completed yet."}
                tone={valueTone(backtestReturn)}
              />
              <StatCard
                label="Excess vs benchmark"
                value={formatPercent(backtestExcess)}
                detail={benchmarkReturn !== null ? `Benchmark ${formatPercent(benchmarkReturn)}` : "Benchmark not available yet."}
                tone={valueTone(backtestExcess)}
              />
              <StatCard
                label="Latest run profit"
                value={formatCurrency(latestRunProfit)}
                detail={workspace?.portfolio.status.latest_run?.mode ? toTitleCase(workspace.portfolio.status.latest_run.mode) : "No recent run."}
                tone={valueTone(latestRunProfit)}
              />
              <StatCard
                label="Safe days"
                value={String(workspace?.live.safe_day_counts.paper_and_live ?? 0)}
                detail={`Paper only ${workspace?.paper.paper_safe_days ?? 0}`}
              />
            </div>
          </SectionCard>

          <SectionCard title="Recent orders" description="Latest order intents and fills.">
            <Table
              columns={["Stock", "Action", "Status", "Shares", "Price", "When"]}
              rows={(workspace?.portfolio.latest_orders ?? []).map((order) => [
                <strong key={`${order.id}-stock`}>{order.symbol}</strong>,
                toTitleCase(order.side),
                toTitleCase(order.status),
                formatNumber(order.requested_shares, 2),
                formatCurrency(order.limit_price ?? order.reference_price, 2),
                formatDateTime(order.created_at)
              ])}
              emptyMessage="No recent orders are recorded."
            />
            <Table
              columns={["Stock", "Fill status", "Filled shares", "Price", "Slippage", "When"]}
              rows={(workspace?.portfolio.latest_fills ?? []).map((fill) => [
                <strong key={`${fill.id}-fill`}>{fill.symbol}</strong>,
                toTitleCase(fill.fill_status),
                formatNumber(fill.filled_shares, 2),
                formatCurrency(fill.fill_price, 2),
                `${fill.slippage_bps.toFixed(1)} bps`,
                formatDateTime(fill.filled_at)
              ])}
              emptyMessage="No fills are recorded yet."
            />
          </SectionCard>

          <SectionCard title="Recent activity" description="A clean log of what changed most recently.">
            <ActivityFeed items={activityItems} />
          </SectionCard>
        </div>
      ) : null}

      {activeScreen === "setup" ? (
        <div className="screen-grid">
          <SectionCard
            title="First-run checklist"
            description="Use this order if you are setting up the app for the first time."
            actions={
              <button
                type="button"
                className="button"
                disabled={activeAction === "save-setup"}
                onClick={() => void saveSetup()}
              >
                {activeAction === "save-setup" ? "Saving..." : "Save setup"}
              </button>
            }
          >
            <SetupStepList items={setupSteps} />
          </SectionCard>

          <SectionCard title="Storage" description="These paths tell the app where to keep its local database, reports, and logs.">
            <div className="form-grid">
              <label>
                <span>Timezone</span>
                <input value={setupDraft.timezone} onChange={(event) => updateDraft("timezone", event.target.value)} />
              </label>
              <label>
                <span>Database path</span>
                <input value={setupDraft.databasePath} onChange={(event) => updateDraft("databasePath", event.target.value)} />
              </label>
              <label>
                <span>Artifacts directory</span>
                <input value={setupDraft.artifactsDir} onChange={(event) => updateDraft("artifactsDir", event.target.value)} />
              </label>
              <label>
                <span>Logs directory</span>
                <input value={setupDraft.logsDir} onChange={(event) => updateDraft("logsDir", event.target.value)} />
              </label>
            </div>
          </SectionCard>

          <SectionCard title="Market data" description="Pick providers and the list of stocks and ETFs you want the app to follow.">
            <div className="form-grid">
              <label>
                <span>Primary provider</span>
                <select value={setupDraft.primaryProvider} onChange={(event) => updateDraft("primaryProvider", event.target.value)}>
                  <option value="stooq">stooq</option>
                  <option value="alpha_vantage">alpha_vantage</option>
                </select>
              </label>
              <label>
                <span>Secondary provider</span>
                <select value={setupDraft.secondaryProvider} onChange={(event) => updateDraft("secondaryProvider", event.target.value)}>
                  <option value="">none</option>
                  <option value="alpha_vantage">alpha_vantage</option>
                  <option value="stooq">stooq</option>
                </select>
              </label>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={setupDraft.alphaEnabled}
                  onChange={(event) => updateDraft("alphaEnabled", event.target.checked)}
                />
                <span>Use Alpha Vantage as supporting confirmation data</span>
              </label>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={setupDraft.fundamentalsEnabled}
                  onChange={(event) => updateDraft("fundamentalsEnabled", event.target.checked)}
                />
                <span>Enable SEC fundamentals</span>
              </label>
              <label className="form-grid__wide">
                <span>SEC user agent</span>
                <input
                  value={setupDraft.fundamentalsUserAgent}
                  onChange={(event) => updateDraft("fundamentalsUserAgent", event.target.value)}
                />
              </label>
              <label className="form-grid__wide">
                <span>Stock candidates</span>
                <textarea
                  rows={4}
                  value={setupDraft.stockCandidates}
                  onChange={(event) => updateDraft("stockCandidates", event.target.value)}
                />
              </label>
              <label className="form-grid__wide">
                <span>Curated ETFs</span>
                <textarea
                  rows={3}
                  value={setupDraft.curatedEtfs}
                  onChange={(event) => updateDraft("curatedEtfs", event.target.value)}
                />
              </label>
            </div>
          </SectionCard>

          <SectionCard title="Broker and safety" description="These settings are only needed if you plan to move beyond simulation.">
            <div className="form-grid">
              <label className="checkbox form-grid__wide">
                <input
                  type="checkbox"
                  checked={setupDraft.brokerEnabled}
                  onChange={(event) => updateDraft("brokerEnabled", event.target.checked)}
                />
                <span>Enable broker integration</span>
              </label>
              <label>
                <span>Operator name</span>
                <input value={setupDraft.operatorName} onChange={(event) => updateDraft("operatorName", event.target.value)} />
              </label>
              <label>
                <span>Paper account id</span>
                <input value={setupDraft.paperAccountId} onChange={(event) => updateDraft("paperAccountId", event.target.value)} />
              </label>
              <label>
                <span>Live account id</span>
                <input value={setupDraft.liveAccountId} onChange={(event) => updateDraft("liveAccountId", event.target.value)} />
              </label>
              <label>
                <span>Gateway base URL</span>
                <input value={setupDraft.gatewayBaseUrl} onChange={(event) => updateDraft("gatewayBaseUrl", event.target.value)} />
              </label>
              <label>
                <span>Default mode</span>
                <select value={setupDraft.defaultMode} onChange={(event) => updateDraft("defaultMode", event.target.value)}>
                  <option value="simulation">simulation</option>
                  <option value="paper">paper</option>
                </select>
              </label>
              <label>
                <span>Live profile</span>
                <select value={setupDraft.liveProfile} onChange={(event) => updateDraft("liveProfile", event.target.value)}>
                  <option value="manual">manual</option>
                  <option value="autonomous">autonomous</option>
                </select>
              </label>
              <label>
                <span>Daily loss cap</span>
                <input value={setupDraft.dailyLossCap} onChange={(event) => updateDraft("dailyLossCap", event.target.value)} />
              </label>
              <label>
                <span>Drawdown freeze</span>
                <input value={setupDraft.drawdownFreeze} onChange={(event) => updateDraft("drawdownFreeze", event.target.value)} />
              </label>
            </div>
          </SectionCard>
        </div>
      ) : null}
    </main>
  );
}

export default App;
