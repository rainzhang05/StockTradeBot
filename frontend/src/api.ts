import type { WorkspaceSnapshot } from "./types";

export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function appendQuery(url: string, params: Record<string, unknown>): string {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === "") {
      return;
    }

    if (Array.isArray(value)) {
      value.forEach((item) => {
        query.append(key, String(item));
      });
      return;
    }

    query.set(key, String(value));
  });

  const serialized = query.toString();
  return serialized ? `${url}?${serialized}` : url;
}

async function readJson<T>(response: Response): Promise<T> {
  const payload = (await response.json()) as T | { detail?: string };
  if (!response.ok) {
    const message =
      typeof payload === "object" && payload !== null && "detail" in payload
        ? String(payload.detail)
        : `Request failed with status ${response.status}`;
    throw new ApiError(message, response.status);
  }
  return payload as T;
}

async function requestJson<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(path, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {})
    },
    ...init
  });
  return readJson<T>(response);
}

export function fetchWorkspace(): Promise<WorkspaceSnapshot> {
  return requestJson<WorkspaceSnapshot>("/api/v1/operator/workspace");
}

export function repairStrategyModeResources(
  asOf?: string,
): Promise<{ repair: Record<string, unknown> }> {
  const url = appendQuery("/api/v1/operator/strategy-modes/repair", { as_of: asOf });
  return requestJson(url, { method: "POST" });
}

export function updateConfig(patch: Record<string, unknown>): Promise<{ config: Record<string, unknown> }> {
  return requestJson<{ config: Record<string, unknown> }>("/api/v1/config", {
    method: "PUT",
    body: JSON.stringify(patch)
  });
}

export function updateMode(
  targetMode: string,
  ackDisableApprovals = false,
): Promise<{ mode_transition: Record<string, unknown> }> {
  const url = appendQuery("/api/v1/system/mode", {
    target_mode: targetMode,
    ack_disable_approvals: ackDisableApprovals
  });
  return requestJson(url, { method: "POST" });
}

export function backfillMarketData(input: {
  asOf?: string;
  lookbackDays: number;
  symbols: string[];
}): Promise<{ backfill_run: Record<string, unknown> }> {
  const url = appendQuery("/api/v1/market-data/backfill", {
    as_of: input.asOf,
    lookback_days: input.lookbackDays,
    symbol: input.symbols
  });
  return requestJson(url, { method: "POST" });
}

export function buildDataset(asOf?: string): Promise<{ snapshot: Record<string, unknown> }> {
  const url = appendQuery("/api/v1/models/datasets/build", { as_of: asOf });
  return requestJson(url, { method: "POST" });
}

export function trainModel(asOf?: string): Promise<{ training_run: Record<string, unknown> }> {
  const url = appendQuery("/api/v1/models/train", { as_of: asOf });
  return requestJson(url, { method: "POST" });
}

export function backtestModel(
  modelVersion?: string,
): Promise<{ backtest_run: Record<string, unknown> }> {
  const url = appendQuery("/api/v1/models/backtests/run", {
    model_version: modelVersion
  });
  return requestJson(url, { method: "POST" });
}

export function runSimulation(input: {
  asOf?: string;
  modelVersion?: string;
}): Promise<{ simulation_run: Record<string, unknown> }> {
  const url = appendQuery("/api/v1/portfolio/simulations/run", {
    as_of: input.asOf,
    model_version: input.modelVersion
  });
  return requestJson(url, { method: "POST" });
}

export function runPaper(input: {
  asOf?: string;
  modelVersion?: string;
}): Promise<{ paper_run: Record<string, unknown> }> {
  const url = appendQuery("/api/v1/paper/run", {
    as_of: input.asOf,
    model_version: input.modelVersion
  });
  return requestJson(url, { method: "POST" });
}

export function runLive(input: {
  asOf?: string;
  modelVersion?: string;
  ackDisableApprovals?: boolean;
}): Promise<Record<string, Record<string, unknown>>> {
  const url = appendQuery("/api/v1/live/run", {
    as_of: input.asOf,
    model_version: input.modelVersion,
    ack_disable_approvals: input.ackDisableApprovals ?? false
  });
  return requestJson(url, { method: "POST" });
}

export function approveLive(input: {
  runId?: number;
  approveAll?: boolean;
  approveSymbols?: string[];
  rejectSymbols?: string[];
}): Promise<{ approval_result: Record<string, unknown> }> {
  const url = appendQuery("/api/v1/live/approvals", {
    run_id: input.runId,
    approve_all: input.approveAll ?? false,
    approve_symbol: input.approveSymbols ?? [],
    reject_symbol: input.rejectSymbols ?? []
  });
  return requestJson(url, { method: "POST" });
}
