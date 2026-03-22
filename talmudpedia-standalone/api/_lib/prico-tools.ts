import type {
  ClientActivitySummaryRequest,
  ConcentrationRequest,
  DealScopedRequest,
  PricoWidgetOutputRequest,
} from "../../server/prico-demo/contracts.js";
import {
  getBankConcentration,
  getClientActivitySummary,
  getCurrencyConcentration,
  getDealExplainer,
  getMarketContext,
} from "../../server/prico-demo/service.js";
import { renderPricoWidgetOutput } from "../../server/prico-demo/widget-output-service.js";
import { toPricoErrorPayload } from "./errors.js";
import { json } from "./http.js";

async function readJson<T>(request: Request): Promise<T> {
  return (await request.json()) as T;
}

export async function handleClientActivitySummary(request: Request): Promise<Response> {
  try {
    return json(await getClientActivitySummary(await readJson<ClientActivitySummaryRequest>(request)));
  } catch (error) {
    const payload = toPricoErrorPayload(error);
    return json(payload, { status: payload.status });
  }
}

export async function handleBankConcentration(request: Request): Promise<Response> {
  try {
    return json(await getBankConcentration(await readJson<ConcentrationRequest>(request)));
  } catch (error) {
    const payload = toPricoErrorPayload(error);
    return json(payload, { status: payload.status });
  }
}

export async function handleCurrencyConcentration(request: Request): Promise<Response> {
  try {
    return json(await getCurrencyConcentration(await readJson<ConcentrationRequest>(request)));
  } catch (error) {
    const payload = toPricoErrorPayload(error);
    return json(payload, { status: payload.status });
  }
}

export async function handleDealExplainer(request: Request): Promise<Response> {
  try {
    return json(await getDealExplainer(await readJson<DealScopedRequest>(request)));
  } catch (error) {
    const payload = toPricoErrorPayload(error);
    return json(payload, { status: payload.status });
  }
}

export async function handleMarketContext(request: Request): Promise<Response> {
  try {
    return json(await getMarketContext(await readJson<DealScopedRequest>(request)));
  } catch (error) {
    const payload = toPricoErrorPayload(error);
    return json(payload, { status: payload.status });
  }
}

export async function handleWidgetOutput(request: Request): Promise<Response> {
  try {
    return json(await renderPricoWidgetOutput(await readJson<PricoWidgetOutputRequest>(request)));
  } catch (error) {
    const payload = toPricoErrorPayload(error);
    return json(payload, { status: payload.status });
  }
}
