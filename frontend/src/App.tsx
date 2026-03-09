import { useEffect, useState } from "react";
import {
  ApiError,
  approveLive,
  backfillMarketData,
  backtestModel,
  buildDataset,
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

type ScreenKey = "setup" | "dashboard" | "portfolio" | "orders" | "research" | "data" | "system";

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

const screens: Array<{ key: ScreenKey; label: string }> = [
  { key: "setup", label: "Setup" },
  { key: "dashboard", label: "Dashboard" },
  { key: "portfolio", label: "Portfolio" },
  { key: "orders", label: "Orders" },
  { key: "research", label: "Research" },
  { key: "data", label: "Data" },
  { key: "system", label: "System" }
];

function readHashScreen(): ScreenKey {
  const hash = window.location.hash.replace("#", "");
  return screens.some((screen) => screen.key === hash) ? (hash as ScreenKey) : "dashboard";
}

function writeHashScreen(screen: ScreenKey): void {
  window.location.hash = screen;
}

function formatCurrency(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return "n/a";
  }
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0
  }).format(value);
}

function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return "n/a";
  }
  return `${(value * 100).toFixed(1)}%`;
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

function statusTone(ok: boolean): string {
  return ok ? "neutral" : "alert";
}

function modeTone(mode: string | null | undefined): string {
  if (!mode) {
    return "muted";
  }
  if (mode.startsWith("live")) {
    return "alert";
  }
  if (mode === "paper") {
    return "accent";
  }
  if (mode === "frozen") {
    return "alert";
  }
  return "neutral";
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

function StatusPill(props: { label: string; tone?: string }): JSX.Element {
  return <span className={`status-pill status-pill--${props.tone ?? "neutral"}`}>{props.label}</span>;
}

function MetricCard(props: { label: string; value: string; detail?: string; tone?: string }): JSX.Element {
  return (
    <article className={`metric-card metric-card--${props.tone ?? "neutral"}`}>
      <p className="metric-card__label">{props.label}</p>
      <p className="metric-card__value">{props.value}</p>
      {props.detail ? <p className="metric-card__detail">{props.detail}</p> : null}
    </article>
  );
}

function Section(props: {
  title: string;
  description?: string;
  actions?: JSX.Element;
  children: JSX.Element | JSX.Element[] | null;
}): JSX.Element {
  return (
    <section className="panel">
      <div className="panel__header">
        <div>
          <p className="panel__eyebrow">{props.title}</p>
          {props.description ? <p className="panel__description">{props.description}</p> : null}
        </div>
        {props.actions ? <div className="panel__actions">{props.actions}</div> : null}
      </div>
      {props.children}
    </section>
  );
}

function KeyValueList(props: { rows: Array<{ label: string; value: string }> }): JSX.Element {
  return (
    <dl className="key-value-list">
      {props.rows.map((row) => (
        <div className="key-value-list__row" key={row.label}>
          <dt>{row.label}</dt>
          <dd>{row.value}</dd>
        </div>
      ))}
    </dl>
  );
}

function AuditFeed(props: { items: AuditEvent[] }): JSX.Element {
  if (props.items.length === 0) {
    return <p className="empty-state">No audit events recorded yet.</p>;
  }

  return (
    <div className="timeline">
      {props.items.map((item) => (
        <article className="timeline__item" key={item.id}>
          <div className="timeline__meta">
            <StatusPill label={item.category} tone="muted" />
            <span>{formatDateTime(item.created_at)}</span>
          </div>
          <p>{item.message}</p>
        </article>
      ))}
    </div>
  );
}

function OperationalLogFeed(props: { items: OperationalLogEvent[] }): JSX.Element {
  if (props.items.length === 0) {
    return <p className="empty-state">No operational logs recorded yet.</p>;
  }

  return (
    <div className="timeline">
      {props.items.map((item, index) => (
        <article className="timeline__item" key={`${item.timestamp ?? "missing"}-${item.category}-${index}`}>
          <div className="timeline__meta">
            <StatusPill
              label={item.level}
              tone={item.level === "error" ? "alert" : item.level === "warning" ? "accent" : "muted"}
            />
            <StatusPill label={item.category} tone="muted" />
            <span>{formatDateTime(item.timestamp)}</span>
          </div>
          <p>{item.message}</p>
          {Object.keys(item.details).length > 0 ? (
            <pre className="log-details">{JSON.stringify(item.details, null, 2)}</pre>
          ) : null}
        </article>
      ))}
    </div>
  );
}

function ChecksList(props: { checks: Array<HealthCheck | LiveGateCheck> }): JSX.Element {
  return (
    <div className="checks-list">
      {props.checks.map((check) => (
        <article className="check-row" key={check.name}>
          <div>
            <p className="check-row__title">{check.name}</p>
            <p className="check-row__detail">{check.detail}</p>
          </div>
          <StatusPill label={check.ok ? "pass" : "blocked"} tone={statusTone(check.ok)} />
        </article>
      ))}
    </div>
  );
}

function DataTable(props: {
  columns: string[];
  rows: Array<Array<JSX.Element | string>>;
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

function App(): JSX.Element {
  const [activeScreen, setActiveScreen] = useState<ScreenKey>(readHashScreen);
  const [workspace, setWorkspace] = useState<WorkspaceSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [activeAction, setActiveAction] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [setupDraft, setSetupDraft] = useState<SetupDraft>(() => initialSetupDraft(null));
  const [setupDirty, setSetupDirty] = useState(false);
  const [backfillSymbols, setBackfillSymbols] = useState("AAPL, MSFT, SPY");
  const [backfillAsOf, setBackfillAsOf] = useState("");
  const [backfillLookbackDays, setBackfillLookbackDays] = useState("180");
  const [researchAsOf, setResearchAsOf] = useState("");
  const [researchModelVersion, setResearchModelVersion] = useState("");
  const [ackDisableApprovals, setAckDisableApprovals] = useState(false);

  const config = (workspace?.config ?? null) as Record<string, any> | null;
  const modeState = workspace?.risk.mode_state ?? null;
  const pendingApprovals =
    workspace?.live.latest_approvals.filter((item) => item.status === "pending") ?? [];
  const latestTarget = workspace?.portfolio.latest_target_snapshot;
  const topSignals = [...(latestTarget?.positions ?? [])]
    .sort((left, right) => (right.score ?? -999) - (left.score ?? -999))
    .slice(0, 6);

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
    const universe = (workspace.config.universe ?? {}) as Record<string, any>;
    const suggestedSymbols = [
      ...((universe.stock_candidates ?? []) as string[]),
      ...((universe.curated_etfs ?? []) as string[])
    ]
      .slice(0, 8)
      .join(", ");
    if (suggestedSymbols) {
      setBackfillSymbols(suggestedSymbols);
    }
    if (!researchModelVersion && workspace.models.latest_model?.version) {
      setResearchModelVersion(workspace.models.latest_model.version);
    }
  }, [workspace, setupDirty, researchModelVersion]);

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

    await runAction("save-setup", () => updateConfig(patch), "Configuration saved.");
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
      label: "Storage paths configured",
      ok: workspace?.setup.initialized ?? false
    },
    {
      label: "Primary data provider ready",
      ok: workspace?.health.checks.some((check) => check.name === "primary-provider" && check.ok) ?? false
    },
    {
      label: "Secondary data corroboration configured",
      ok: Boolean((config?.data_providers?.secondary_provider as string | null | undefined) ?? null)
    },
    {
      label: "SEC fundamentals configured",
      ok: workspace?.health.checks.some((check) => check.name === "fundamentals-provider" && check.ok) ?? false
    },
    {
      label: "Broker details saved",
      ok: Boolean(config?.broker?.paper_account_id) && Boolean(config?.broker?.live_account_id)
    },
    {
      label: "Readiness checks passing",
      ok: workspace?.health.status === "ok"
    },
    {
      label: "Landed in simulation mode",
      ok: modeState?.current_mode === "simulation"
    }
  ];

  const latestJobs = [
    {
      label: "Backfill",
      status: workspace?.market_data.latest_run?.status ?? "not run",
      detail: workspace?.market_data.latest_run?.completed_at
        ? formatDateTime(workspace.market_data.latest_run.completed_at)
        : "No completed backfill yet."
    },
    {
      label: "Dataset",
      status: workspace?.datasets.latest_dataset_snapshot ? "ready" : "missing",
      detail: workspace?.datasets.latest_dataset_snapshot?.created_at
        ? formatDateTime(workspace.datasets.latest_dataset_snapshot.created_at)
        : "No dataset snapshot yet."
    },
    {
      label: "Training",
      status: workspace?.models.latest_training_run?.status ?? "not run",
      detail: workspace?.models.latest_training_run?.completed_at
        ? formatDateTime(workspace.models.latest_training_run.completed_at)
        : "No training run yet."
    },
    {
      label: "Backtest",
      status: workspace?.models.latest_backtest_run?.status ?? "not run",
      detail: workspace?.models.latest_backtest_run?.completed_at
        ? formatDateTime(workspace.models.latest_backtest_run.completed_at)
        : "No backtest run yet."
    },
    {
      label: "Simulation",
      status: workspace?.portfolio.status.latest_run?.status ?? "not run",
      detail: workspace?.portfolio.status.latest_run?.completed_at
        ? formatDateTime(workspace.portfolio.status.latest_run.completed_at)
        : "No simulation run yet."
    }
  ];

  if (loading && workspace === null) {
    return (
      <main className="app-shell">
        <section className="hero-panel">
          <p className="hero-panel__eyebrow">Phase 8</p>
          <h1>StockTradeBot Operator Console</h1>
          <p>Loading the local control surface.</p>
        </section>
      </main>
    );
  }

  return (
    <main className="app-shell">
      <header className="hero-panel">
        <div>
          <p className="hero-panel__eyebrow">Phase 8</p>
          <h1>StockTradeBot Operator Console</h1>
          <p className="hero-panel__copy">
            Install, configure, monitor, and control the local trading stack from one browser
            surface. Every control path remains explicit and audit-friendly.
          </p>
        </div>
        <div className="hero-panel__status">
          <StatusPill label={workspace?.health.status ?? "offline"} tone={workspace?.health.status === "ok" ? "neutral" : "alert"} />
          <StatusPill label={modeState?.current_mode ?? "simulation"} tone={modeTone(modeState?.current_mode)} />
          <StatusPill label={modeState?.live_profile ?? "manual"} tone="muted" />
          {refreshing ? <span className="hero-panel__refresh">Refreshing…</span> : null}
        </div>
      </header>

      {loadError ? <p className="banner banner--error">{loadError}</p> : null}
      {actionError ? <p className="banner banner--error">{actionError}</p> : null}
      {actionMessage ? <p className="banner banner--success">{actionMessage}</p> : null}

      <div className="layout">
        <aside className="sidebar">
          <nav className="nav">
            {screens.map((screen) => (
              <button
                type="button"
                key={screen.key}
                className={screen.key === activeScreen ? "nav__item nav__item--active" : "nav__item"}
                onClick={() => selectScreen(screen.key)}
              >
                <span>{screen.label}</span>
                {screen.key === "orders" && pendingApprovals.length > 0 ? (
                  <StatusPill label={String(pendingApprovals.length)} tone="alert" />
                ) : null}
              </button>
            ))}
          </nav>
          <div className="sidebar__meta">
            <p>UI URL</p>
            <code>{workspace?.health.ui_url ?? "n/a"}</code>
            <p>Config</p>
            <code>{workspace?.setup.config_path ?? "n/a"}</code>
          </div>
        </aside>

        <section className="content">
          {activeScreen === "setup" ? (
            <>
              <Section
                title="Setup Flow"
                description="The setup flow stays honest about readiness. Saving configuration updates the local typed config and refreshes the doctor checks."
                actions={
                  <button
                    type="button"
                    className="button"
                    disabled={activeAction === "save-setup"}
                    onClick={() => void saveSetup()}
                  >
                    {activeAction === "save-setup" ? "Saving…" : "Save Setup"}
                  </button>
                }
              >
                <div className="grid grid--two">
                  <div className="form-stack">
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
                      <input type="checkbox" checked={setupDraft.alphaEnabled} onChange={(event) => updateDraft("alphaEnabled", event.target.checked)} />
                      <span>Enable Alpha Vantage corroboration</span>
                    </label>
                    <label className="checkbox">
                      <input type="checkbox" checked={setupDraft.fundamentalsEnabled} onChange={(event) => updateDraft("fundamentalsEnabled", event.target.checked)} />
                      <span>Enable SEC fundamentals</span>
                    </label>
                    <label>
                      <span>SEC user agent</span>
                      <input value={setupDraft.fundamentalsUserAgent} onChange={(event) => updateDraft("fundamentalsUserAgent", event.target.value)} />
                    </label>
                  </div>
                  <div className="form-stack">
                    <label>
                      <span>Stock candidates</span>
                      <textarea value={setupDraft.stockCandidates} onChange={(event) => updateDraft("stockCandidates", event.target.value)} rows={4} />
                    </label>
                    <label>
                      <span>Curated ETFs</span>
                      <textarea value={setupDraft.curatedEtfs} onChange={(event) => updateDraft("curatedEtfs", event.target.value)} rows={3} />
                    </label>
                    <label className="checkbox">
                      <input type="checkbox" checked={setupDraft.brokerEnabled} onChange={(event) => updateDraft("brokerEnabled", event.target.checked)} />
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
                    <div className="grid grid--two">
                      <label>
                        <span>Daily loss cap</span>
                        <input value={setupDraft.dailyLossCap} onChange={(event) => updateDraft("dailyLossCap", event.target.value)} />
                      </label>
                      <label>
                        <span>Drawdown freeze</span>
                        <input value={setupDraft.drawdownFreeze} onChange={(event) => updateDraft("drawdownFreeze", event.target.value)} />
                      </label>
                    </div>
                  </div>
                </div>
              </Section>

              <Section title="Readiness Checklist" description="The system lands in simulation first and only advances when the contract gates are actually met.">
                <div className="checks-list">
                  {setupSteps.map((step) => (
                    <article className="check-row" key={step.label}>
                      <div>
                        <p className="check-row__title">{step.label}</p>
                      </div>
                      <StatusPill label={step.ok ? "ready" : "pending"} tone={statusTone(step.ok)} />
                    </article>
                  ))}
                </div>
              </Section>
            </>
          ) : null}

          {activeScreen === "dashboard" ? (
            <>
              <Section title="Current State" description="Critical status stays visible at the top of the local dashboard.">
                <div className="metrics-grid">
                  <MetricCard label="Mode" value={modeState?.current_mode ?? "simulation"} tone={modeTone(modeState?.current_mode)} detail={modeState?.requested_mode ? `Requested: ${modeState.requested_mode}` : "No pending mode request."} />
                  <MetricCard label="Freeze" value={workspace?.risk.active_freeze ? "active" : "clear"} tone={workspace?.risk.active_freeze ? "alert" : "neutral"} detail={workspace?.risk.active_freeze?.reason ?? "No active freeze."} />
                  <MetricCard label="Broker" value={workspace?.broker.paper.broker.connectivity?.ok ? "connected" : "not ready"} tone={workspace?.broker.paper.broker.connectivity?.ok ? "neutral" : "alert"} detail={workspace?.broker.paper.broker.message ?? "No broker snapshot."} />
                  <MetricCard label="Pending approvals" value={String(pendingApprovals.length)} tone={pendingApprovals.length > 0 ? "alert" : "neutral"} detail={pendingApprovals.length > 0 ? "Manual review required." : "No pending manual approvals."} />
                  <MetricCard label="Portfolio NAV" value={formatCurrency(workspace?.portfolio.latest_target_snapshot?.nav)} detail={`Cash ${formatCurrency(workspace?.portfolio.latest_target_snapshot?.cash_balance)}`} />
                  <MetricCard label="Day PnL" value={workspace?.portfolio.status.latest_run ? formatCurrency((workspace.portfolio.status.latest_run.end_nav ?? 0) - (workspace.portfolio.status.latest_run.start_nav ?? 0)) : "n/a"} tone={(workspace?.portfolio.status.latest_run?.end_nav ?? 0) >= (workspace?.portfolio.status.latest_run?.start_nav ?? 0) ? "neutral" : "alert"} detail={workspace?.portfolio.status.latest_run?.regime ?? "No latest run."} />
                  <MetricCard label="Active model" value={workspace?.models.latest_model?.version ?? "none"} detail={workspace?.models.latest_model?.promotion_status ?? "research-only"} />
                  <MetricCard label="Dataset" value={workspace?.datasets.latest_dataset_snapshot?.feature_set_version ?? "missing"} detail={workspace?.datasets.latest_dataset_snapshot ? `${workspace.datasets.latest_dataset_snapshot.row_count} rows` : "Build a dataset snapshot first."} />
                </div>
              </Section>

              <Section title="Latest Jobs">
                <div className="checks-list">
                  {latestJobs.map((job) => (
                    <article className="check-row" key={job.label}>
                      <div>
                        <p className="check-row__title">{job.label}</p>
                        <p className="check-row__detail">{job.detail}</p>
                      </div>
                      <StatusPill label={job.status} tone={job.status === "completed" || job.status === "ready" ? "neutral" : "muted"} />
                    </article>
                  ))}
                </div>
              </Section>

              <Section title="Top Signals" description="The signal view is pulled from the latest target portfolio snapshot.">
                <DataTable
                  columns={["Symbol", "Score", "Target", "Sector", "Price", "Market value"]}
                  rows={topSignals.map((position) => [
                    position.symbol,
                    formatNumber(position.score, 4),
                    formatPercent(position.target_weight),
                    position.sector ?? "n/a",
                    formatCurrency(position.price),
                    formatCurrency(position.market_value)
                  ])}
                  emptyMessage="No target portfolio exists yet."
                />
              </Section>
            </>
          ) : null}

          {activeScreen === "portfolio" ? (
            <>
              <Section title="Target Portfolio" description="The optimizer output is shown alongside exposure and turnover.">
                <KeyValueList
                  rows={[
                    { label: "Trade date", value: latestTarget?.trade_date ?? "n/a" },
                    { label: "NAV", value: formatCurrency(latestTarget?.nav) },
                    { label: "Cash", value: formatCurrency(latestTarget?.cash_balance) },
                    { label: "Gross exposure", value: formatPercent(latestTarget?.gross_exposure) },
                    { label: "Net exposure", value: formatPercent(latestTarget?.net_exposure) },
                    { label: "Turnover", value: formatPercent(latestTarget?.turnover_ratio) }
                  ]}
                />
                <DataTable
                  columns={["Symbol", "Target", "Actual", "Shares", "Score", "Sector"]}
                  rows={(latestTarget?.positions ?? []).map((position: PortfolioPosition) => [
                    position.symbol,
                    formatPercent(position.target_weight),
                    formatPercent(position.actual_weight),
                    formatNumber(position.shares, 2),
                    formatNumber(position.score, 4),
                    position.sector ?? "n/a"
                  ])}
                  emptyMessage="No target positions are available."
                />
              </Section>

              <Section title="Broker Snapshot" description="Paper and live holdings are kept separate from model targets.">
                <KeyValueList
                  rows={[
                    { label: "Paper account", value: workspace?.broker.paper.broker.paper_account_id ?? "n/a" },
                    { label: "Live account", value: workspace?.broker.live.broker.live_account_id ?? "n/a" },
                    { label: "Broker connectivity", value: workspace?.broker.paper.broker.connectivity?.detail ?? "not configured" },
                    { label: "Paper safe days", value: String(workspace?.paper.paper_safe_days ?? 0) },
                    { label: "Combined safe days", value: String(workspace?.live.safe_day_counts.paper_and_live ?? 0) }
                  ]}
                />
              </Section>
            </>
          ) : null}

          {activeScreen === "orders" ? (
            <>
              <Section
                title="Execution Controls"
                description="Run paper trading, prepare live-manual approvals, or execute live-autonomous when the gates are satisfied."
                actions={
                  <div className="toolbar">
                    <button type="button" className="button" disabled={activeAction === "paper-run"} onClick={() => void runAction("paper-run", () => runPaper({ asOf: researchAsOf || undefined, modelVersion: researchModelVersion || undefined }), "Paper trading run completed.")}>
                      {activeAction === "paper-run" ? "Running…" : "Run Paper"}
                    </button>
                    <button type="button" className="button" disabled={activeAction === "live-prepare"} onClick={() => void runAction("live-prepare", () => runLive({ asOf: researchAsOf || undefined, modelVersion: researchModelVersion || undefined, ackDisableApprovals }), "Live workflow submitted.")}>
                      {activeAction === "live-prepare" ? "Submitting…" : "Prepare Live"}
                    </button>
                    <label className="checkbox checkbox--inline">
                      <input type="checkbox" checked={ackDisableApprovals} onChange={(event) => setAckDisableApprovals(event.target.checked)} />
                      <span>Acknowledge autonomous approval bypass</span>
                    </label>
                  </div>
                }
              >
                <div className="grid grid--two">
                  <label>
                    <span>As-of date</span>
                    <input value={researchAsOf} onChange={(event) => setResearchAsOf(event.target.value)} placeholder="2026-04-15" />
                  </label>
                  <label>
                    <span>Model version</span>
                    <input value={researchModelVersion} onChange={(event) => setResearchModelVersion(event.target.value)} placeholder="latest model" />
                  </label>
                </div>
              </Section>

              <Section
                title="Manual Approvals"
                description="Every pending live-manual order shows its own approval state. Autonomous mode is not presented as easier."
                actions={
                  pendingApprovals.length > 0 ? (
                    <button type="button" className="button button--danger" disabled={activeAction === "approve-all"} onClick={() => void runAction("approve-all", () => approveLive({ runId: workspace?.live.latest_run?.id, approveAll: true }), "All pending approvals processed.")}>
                      {activeAction === "approve-all" ? "Processing…" : "Approve All"}
                    </button>
                  ) : undefined
                }
              >
                <DataTable
                  columns={["Symbol", "Status", "Requested", "Decision", "Actions"]}
                  rows={pendingApprovals.map((approval: ApprovalSnapshot) => [
                    approval.symbol,
                    approval.status,
                    formatDateTime(approval.created_at),
                    approval.reason ?? "pending",
                    (
                      <div className="row-actions">
                        <button type="button" className="button button--small" disabled={activeAction === `approve-${approval.symbol}`} onClick={() => void approveSingle(approval.symbol)}>
                          Approve
                        </button>
                        <button type="button" className="button button--small button--ghost" disabled={activeAction === `reject-${approval.symbol}`} onClick={() => void rejectSingle(approval.symbol)}>
                          Reject
                        </button>
                      </div>
                    )
                  ])}
                  emptyMessage="No pending approvals."
                />
              </Section>

              <Section title="Recent Orders and Fills">
                <DataTable
                  columns={["Symbol", "Side", "Status", "Type", "Shares", "Target"]}
                  rows={(workspace?.portfolio.latest_orders ?? []).map((order: OrderSnapshot) => [
                    order.symbol,
                    order.side,
                    order.status,
                    order.order_type,
                    formatNumber(order.requested_shares, 2),
                    formatPercent(order.target_weight)
                  ])}
                  emptyMessage="No recent orders are recorded."
                />
                <DataTable
                  columns={["Symbol", "Side", "Fill status", "Filled shares", "Price", "Slippage"]}
                  rows={(workspace?.portfolio.latest_fills ?? []).map((fill: FillSnapshot) => [
                    fill.symbol,
                    fill.side,
                    fill.fill_status,
                    formatNumber(fill.filled_shares, 2),
                    formatCurrency(fill.fill_price),
                    `${fill.slippage_bps.toFixed(1)} bps`
                  ])}
                  emptyMessage="No fills are recorded yet."
                />
              </Section>
            </>
          ) : null}

          {activeScreen === "research" ? (
            <>
              <Section
                title="Research Actions"
                description="The UI drives the same backend research jobs as the CLI. Nothing bypasses the documented APIs."
                actions={
                  <div className="toolbar">
                    <button type="button" className="button" disabled={activeAction === "build-dataset"} onClick={() => void runAction("build-dataset", () => buildDataset(researchAsOf || undefined), "Dataset snapshot built.")}>
                      {activeAction === "build-dataset" ? "Building…" : "Build Dataset"}
                    </button>
                    <button type="button" className="button" disabled={activeAction === "train-model"} onClick={() => void runAction("train-model", () => trainModel(researchAsOf || undefined), "Training run completed.")}>
                      {activeAction === "train-model" ? "Training…" : "Train Model"}
                    </button>
                    <button type="button" className="button" disabled={activeAction === "backtest-model"} onClick={() => void runAction("backtest-model", () => backtestModel(researchModelVersion || undefined), "Backtest run completed.")}>
                      {activeAction === "backtest-model" ? "Backtesting…" : "Run Backtest"}
                    </button>
                    <button type="button" className="button" disabled={activeAction === "simulate-run"} onClick={() => void runAction("simulate-run", () => runSimulation({ asOf: researchAsOf || undefined, modelVersion: researchModelVersion || undefined }), "Simulation run completed.")}>
                      {activeAction === "simulate-run" ? "Simulating…" : "Run Simulation"}
                    </button>
                  </div>
                }
              >
                <div className="grid grid--two">
                  <label>
                    <span>As-of date</span>
                    <input value={researchAsOf} onChange={(event) => setResearchAsOf(event.target.value)} placeholder="2026-04-15" />
                  </label>
                  <label>
                    <span>Model version</span>
                    <input value={researchModelVersion} onChange={(event) => setResearchModelVersion(event.target.value)} placeholder="latest model" />
                  </label>
                </div>
              </Section>

              <Section title="Dataset and Model Snapshot">
                <div className="metrics-grid">
                  <MetricCard label="Latest dataset" value={workspace?.datasets.latest_dataset_snapshot?.feature_set_version ?? "missing"} detail={workspace?.datasets.latest_dataset_snapshot ? `${workspace.datasets.latest_dataset_snapshot.row_count} rows` : "Run dataset build first."} />
                  <MetricCard label="Model version" value={workspace?.models.latest_model?.version ?? "none"} detail={workspace?.models.latest_model?.promotion_status ?? "research-only"} />
                  <MetricCard label="Validation folds" value={workspace?.models.latest_validation_run ? String(workspace.models.latest_validation_run.fold_count) : "0"} detail={workspace?.models.latest_validation_run?.status ?? "No validation run yet."} />
                  <MetricCard label="Backtest" value={workspace?.models.latest_backtest_run?.status ?? "not run"} detail={workspace?.models.latest_backtest_run?.benchmark_symbol ?? "No benchmark yet."} />
                </div>
                <KeyValueList
                  rows={[
                    { label: "Feature versions", value: workspace?.datasets.feature_set_versions.map((item) => item.version).join(", ") || "none" },
                    { label: "Label versions", value: workspace?.datasets.label_versions.map((item) => item.version).join(", ") || "none" },
                    { label: "Promotion reasons", value: workspace?.models.latest_model?.promotion_reasons.join(", ") || "none" },
                    { label: "Backtest artifact", value: workspace?.models.latest_backtest_run?.artifact_path ?? "n/a" }
                  ]}
                />
              </Section>
            </>
          ) : null}

          {activeScreen === "data" ? (
            <>
              <Section
                title="Market Data Control"
                description="Backfills stay explicit so the operator can see universe shape, provider corroboration, and incident counts."
                actions={
                  <button type="button" className="button" disabled={activeAction === "backfill"} onClick={() => void runAction("backfill", () => backfillMarketData({ asOf: backfillAsOf || undefined, lookbackDays: Number(backfillLookbackDays), symbols: parseSymbolList(backfillSymbols) }), "Market-data backfill completed.")}>
                    {activeAction === "backfill" ? "Backfilling…" : "Run Backfill"}
                  </button>
                }
              >
                <div className="grid grid--three">
                  <label>
                    <span>Symbols</span>
                    <textarea value={backfillSymbols} onChange={(event) => setBackfillSymbols(event.target.value)} rows={3} />
                  </label>
                  <label>
                    <span>As-of date</span>
                    <input value={backfillAsOf} onChange={(event) => setBackfillAsOf(event.target.value)} placeholder="2026-04-15" />
                  </label>
                  <label>
                    <span>Lookback days</span>
                    <input value={backfillLookbackDays} onChange={(event) => setBackfillLookbackDays(event.target.value)} />
                  </label>
                </div>
              </Section>

              <Section title="Data Quality">
                <div className="metrics-grid">
                  <MetricCard label="Latest backfill" value={workspace?.market_data.latest_run?.status ?? "not run"} detail={workspace?.market_data.latest_run?.completed_at ? formatDateTime(workspace.market_data.latest_run.completed_at) : "No completed backfill."} />
                  <MetricCard label="Universe" value={workspace?.market_data.latest_universe_snapshot ? `${workspace.market_data.latest_universe_snapshot.stock_count} stocks` : "missing"} detail={workspace?.market_data.latest_universe_snapshot ? `${workspace.market_data.latest_universe_snapshot.etf_count} ETFs` : "No universe snapshot."} />
                  <MetricCard label="Verified bars" value={String(workspace?.market_data.validation_counts.verified ?? 0)} detail={`Provisional ${workspace?.market_data.validation_counts.provisional ?? 0}`} />
                  <MetricCard label="Fundamentals" value={String(workspace?.market_data.fundamentals_observation_count ?? 0)} detail="Availability-aware SEC observations." />
                </div>
                <DataTable
                  columns={["Symbol", "Date", "Domain", "Status", "Providers"]}
                  rows={(workspace?.market_data.recent_incidents ?? []).map((incident) => [
                    incident.symbol,
                    incident.trade_date,
                    incident.domain,
                    incident.resolution_status,
                    incident.involved_providers.join(", ")
                  ])}
                  emptyMessage="No unresolved or recent data incidents."
                />
              </Section>
            </>
          ) : null}

          {activeScreen === "system" ? (
            <>
              <Section
                title="Mode Controls"
                description="Mode changes stay deliberate. Live-manual remains the default live profile and autonomous mode demands an explicit acknowledgement."
                actions={
                  <div className="toolbar">
                    <button type="button" className="button" disabled={activeAction === "mode-simulation"} onClick={() => void runAction("mode-simulation", () => updateMode("simulation"), "System switched to simulation mode.")}>
                      {activeAction === "mode-simulation" ? "Switching…" : "Simulation"}
                    </button>
                    <button type="button" className="button" disabled={activeAction === "mode-paper"} onClick={() => void runAction("mode-paper", () => updateMode("paper"), "System entered paper mode.")}>
                      {activeAction === "mode-paper" ? "Switching…" : "Paper"}
                    </button>
                    <button type="button" className="button" disabled={activeAction === "mode-live-manual"} onClick={() => void runAction("mode-live-manual", () => updateMode("live-manual"), "Live-manual arm request submitted.")}>
                      {activeAction === "mode-live-manual" ? "Arming…" : "Live Manual"}
                    </button>
                    <button type="button" className="button button--danger" disabled={activeAction === "mode-live-autonomous"} onClick={() => void runAction("mode-live-autonomous", () => updateMode("live-autonomous", ackDisableApprovals), "Live-autonomous arm request submitted.")}>
                      {activeAction === "mode-live-autonomous" ? "Arming…" : "Live Autonomous"}
                    </button>
                    <label className="checkbox checkbox--inline">
                      <input type="checkbox" checked={ackDisableApprovals} onChange={(event) => setAckDisableApprovals(event.target.checked)} />
                      <span>Acknowledge approval bypass</span>
                    </label>
                  </div>
                }
              >
                <div className="grid grid--two">
                  <div>
                    <p className="subtle-heading">Manual gate checks</p>
                    <ChecksList checks={workspace?.live.gates.manual.checks ?? []} />
                  </div>
                  <div>
                    <p className="subtle-heading">Autonomous gate checks</p>
                    <ChecksList checks={workspace?.live.gates.autonomous.checks ?? []} />
                  </div>
                </div>
              </Section>

              <Section title="Doctor Checks and Audit Trail">
                <div className="grid grid--two">
                  <div>
                    <p className="subtle-heading">Doctor checks</p>
                    <ChecksList checks={workspace?.health.checks ?? []} />
                  </div>
                  <div>
                    <p className="subtle-heading">Audit events</p>
                    <AuditFeed items={workspace?.system.audit_events ?? []} />
                  </div>
                </div>
              </Section>

              <Section title="Operational Logs" description="Recent structured runtime events from the local logs directory help explain failures that are broader than a single audit event.">
                <OperationalLogFeed items={workspace?.system.logs ?? []} />
              </Section>

              <Section title="System Snapshot">
                <KeyValueList
                  rows={[
                    { label: "Initialized", value: String(workspace?.setup.initialized ?? false) },
                    { label: "Database", value: workspace?.setup.database_path ?? "n/a" },
                    { label: "Mode", value: workspace?.system.status.mode ? String(workspace.system.status.mode) : "n/a" },
                    { label: "Schema version", value: workspace?.system.status.schema_version ? String(workspace.system.status.schema_version) : "n/a" },
                    { label: "App home", value: workspace?.system.status.app_home ? String(workspace.system.status.app_home) : "n/a" },
                    { label: "Logs dir", value: workspace?.config.logs_dir ? String(workspace.config.logs_dir) : "n/a" }
                  ]}
                />
              </Section>
            </>
          ) : null}
        </section>
      </div>
    </main>
  );
}

export default App;
