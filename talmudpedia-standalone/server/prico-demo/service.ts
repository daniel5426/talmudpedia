import type {
  ClientActivitySummaryRequest,
  ConcentrationRequest,
  ConcentrationRow,
  DealExplainerResponse,
  DealScopedRequest,
  DemoBenchmark,
  DemoClient,
  DemoDeal,
  MarketContextResponse,
  PricoSummaryMetricSet,
  RecentDealRow,
} from "./contracts.js";
import { PricoToolError } from "./contracts.js";
import { DEMO_BENCHMARKS, DEMO_CLIENTS, DEMO_DEALS } from "./data.js";

function requireClient(clientId: string): DemoClient {
  const normalized = String(clientId || "").trim();
  if (!normalized) {
    throw new PricoToolError("CLIENT_ID_REQUIRED", "client_id is required.", 400);
  }
  const client = DEMO_CLIENTS.find((item) => item.id === normalized);
  if (!client) {
    throw new PricoToolError("CLIENT_NOT_FOUND", `Unknown demo client '${normalized}'.`, 404);
  }
  return client;
}

function requireDeal(clientId: string, dealId: string): DemoDeal {
  const normalizedDealId = String(dealId || "").trim();
  if (!normalizedDealId) {
    throw new PricoToolError("DEAL_ID_REQUIRED", "deal_id is required.", 400);
  }
  const deal = DEMO_DEALS.find(
    (item) => item.clientId === clientId && item.dealId === normalizedDealId,
  );
  if (!deal) {
    throw new PricoToolError(
      "DEAL_NOT_FOUND",
      `Deal '${normalizedDealId}' was not found for client '${clientId}'.`,
      404,
    );
  }
  return deal;
}

function inDateWindow(deal: DemoDeal, dateFrom?: string, dateTo?: string): boolean {
  if (dateFrom && deal.executionDate < dateFrom) return false;
  if (dateTo && deal.executionDate > dateTo) return false;
  return true;
}

function getDealsForClient(payload: ConcentrationRequest): DemoDeal[] {
  const client = requireClient(payload.client_id);
  const matches = DEMO_DEALS.filter(
    (deal) =>
      deal.clientId === client.id &&
      inDateWindow(deal, payload.date_from, payload.date_to),
  ).sort((left, right) => right.executionDate.localeCompare(left.executionDate));
  return matches;
}

function summarizeTrend(deals: DemoDeal[]): string {
  if (deals.length === 0) return "no_recent_activity";
  const counts = new Map<string, number>();
  for (const deal of deals) {
    counts.set(deal.executionDate, (counts.get(deal.executionDate) || 0) + 1);
  }
  const top = [...counts.entries()].sort((a, b) => b[1] - a[1])[0];
  if (!top) return "no_recent_activity";
  return top[1] > 1 ? `clustered_on_${top[0]}` : `steady_activity_through_${top[0]}`;
}

function topLabels<K extends string>(items: DemoDeal[], key: (deal: DemoDeal) => K): string[] {
  const counts = new Map<K, number>();
  for (const item of items) {
    counts.set(key(item), (counts.get(key(item)) || 0) + 1);
  }
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 3)
    .map(([label]) => String(label));
}

function concentrationRows(
  deals: DemoDeal[],
  key: (deal: DemoDeal) => string,
): ConcentrationRow[] {
  const total = deals.reduce((sum, deal) => sum + deal.notional, 0);
  const buckets = new Map<
    string,
    { dealCount: number; notionalProxy: number }
  >();
  for (const deal of deals) {
    const label = key(deal);
    const bucket = buckets.get(label) || { dealCount: 0, notionalProxy: 0 };
    bucket.dealCount += 1;
    bucket.notionalProxy += deal.notional;
    buckets.set(label, bucket);
  }
  return [...buckets.entries()]
    .map(([label, bucket]) => ({
      label,
      deal_count: bucket.dealCount,
      notional_proxy: bucket.notionalProxy,
      share_pct: total > 0 ? Number(((bucket.notionalProxy / total) * 100).toFixed(1)) : 0,
    }))
    .sort((a, b) => b.notional_proxy - a.notional_proxy);
}

function benchmarkForDeal(deal: DemoDeal): DemoBenchmark | null {
  return (
    DEMO_BENCHMARKS.find(
      (item) => item.currencyPair === deal.currencyPair && item.date === deal.executionDate,
    ) || null
  );
}

export function listDemoClients(): DemoClient[] {
  return DEMO_CLIENTS;
}

export function getClientActivitySummary(payload: ClientActivitySummaryRequest) {
  const client = requireClient(payload.client_id);
  const currencies = Array.isArray(payload.currencies)
    ? payload.currencies.map((item) => String(item).trim()).filter(Boolean)
    : [];
  const deals = getDealsForClient(payload).filter((deal) =>
    currencies.length > 0 ? currencies.includes(deal.currency) : true,
  );

  const summary: PricoSummaryMetricSet = {
    deal_count: deals.length,
    total_notional_proxy: deals.reduce((sum, deal) => sum + deal.notional, 0),
    top_currencies: topLabels(deals, (deal) => deal.currency),
    top_banks: topLabels(deals, (deal) => deal.bank),
    activity_trend: summarizeTrend(deals),
  };

  const recentDeals: RecentDealRow[] = deals.slice(0, 8).map((deal) => ({
    deal_id: deal.dealId,
    currency: deal.currency,
    bank: deal.bank,
    execution_date: deal.executionDate,
    notional: deal.notional,
    rate: deal.rate,
  }));

  return {
    client: {
      client_id: client.id,
      client_name: client.name,
      sector: client.sector,
      base_currency: client.baseCurrency,
    },
    summary,
    deals: recentDeals,
    filters_used: {
      client_id: client.id,
      date_from: payload.date_from || null,
      date_to: payload.date_to || null,
      currencies,
    },
    data_quality_notes:
      deals.length === 0
        ? ["No deals matched the current date/currency filter in the demo dataset."]
        : [],
    source_tables_used: [
      "prico.iskaot",
      "prico.bankim",
      "prico.nigrarot_bankaiyot",
      "prico.paku",
      "prico.ssars",
    ],
  };
}

export function getBankConcentration(payload: ConcentrationRequest) {
  const client = requireClient(payload.client_id);
  const deals = getDealsForClient(payload);
  const rows = concentrationRows(deals, (deal) => deal.bank).map((row) => ({
    bank: row.label,
    deal_count: row.deal_count,
    notional_proxy: row.notional_proxy,
    share_pct: row.share_pct,
  }));

  return {
    client: {
      client_id: client.id,
      client_name: client.name,
    },
    rows,
    risk_flags:
      rows.length > 0 && rows[0].share_pct >= 60
        ? [`${rows[0].bank} concentration is above the demo threshold.`]
        : [],
    filters_used: {
      client_id: client.id,
      date_from: payload.date_from || null,
      date_to: payload.date_to || null,
    },
    data_quality_notes:
      rows.length === 0 ? ["No bank concentration rows were available for the selected window."] : [],
    source_tables_used: ["prico.iskaot", "prico.bankim", "prico.nigrarot_bankaiyot"],
  };
}

export function getCurrencyConcentration(payload: ConcentrationRequest) {
  const client = requireClient(payload.client_id);
  const deals = getDealsForClient(payload);
  const rows = concentrationRows(deals, (deal) => deal.currency).map((row) => ({
    currency: row.label,
    deal_count: row.deal_count,
    notional_proxy: row.notional_proxy,
    share_pct: row.share_pct,
  }));

  return {
    client: {
      client_id: client.id,
      client_name: client.name,
    },
    rows,
    risk_flags:
      rows.length > 0 && rows[0].share_pct >= 65
        ? [`${rows[0].currency} dominates recent activity for this client.`]
        : [],
    filters_used: {
      client_id: client.id,
      date_from: payload.date_from || null,
      date_to: payload.date_to || null,
    },
    data_quality_notes:
      rows.length === 0 ? ["No currency concentration rows were available for the selected window."] : [],
    source_tables_used: ["prico.iskaot", "prico.matbeot", "prico.paku", "prico.ssars"],
  };
}

export function getDealExplainer(payload: DealScopedRequest): DealExplainerResponse {
  const client = requireClient(payload.client_id);
  const deal = requireDeal(client.id, payload.deal_id);

  return {
    deal: {
      deal_id: deal.dealId,
      client_id: client.id,
      bank: deal.bank,
      currency: deal.currency,
      currency_pair: deal.currencyPair,
      execution_date: deal.executionDate,
      rate: deal.rate,
      notional: deal.notional,
      product_family: deal.productFamily,
    },
    timeline: deal.timeline,
    related_metrics: {
      exposure_total: deal.exposureTotal,
    },
    warnings:
      deal.timeline.length < 2
        ? ["Related post-deal timeline data is sparse in the demo dataset."]
        : [],
    source_tables_used: deal.sourceTablesUsed,
  };
}

export function getMarketContext(payload: DealScopedRequest): MarketContextResponse {
  const client = requireClient(payload.client_id);
  const deal = requireDeal(client.id, payload.deal_id);
  const benchmark = benchmarkForDeal(deal);

  if (!benchmark) {
    return {
      deal_context: {
        deal_id: deal.dealId,
        client_id: client.id,
        currency_pair: deal.currencyPair,
        deal_rate: deal.rate,
        deal_date: deal.executionDate,
      },
      benchmark: {
        source: "unavailable",
        benchmark_rate: null,
        confidence: "low",
      },
      comparison: {
        delta: null,
        assessment: "benchmark_unavailable",
      },
      warnings: ["No benchmark entry was available for this deal date in the demo dataset."],
    };
  }

  const delta = Number((deal.rate - benchmark.rate).toFixed(4));
  let assessment = "within_normal_range";
  if (Math.abs(delta) >= 0.05) {
    assessment = "materially_different";
  } else if (Math.abs(delta) >= 0.02) {
    assessment = "slightly_different";
  }

  return {
    deal_context: {
      deal_id: deal.dealId,
      client_id: client.id,
      currency_pair: deal.currencyPair,
      deal_rate: deal.rate,
      deal_date: deal.executionDate,
    },
    benchmark: {
      source: benchmark.source,
      benchmark_rate: benchmark.rate,
      confidence: benchmark.confidence,
    },
    comparison: {
      delta,
      assessment,
    },
    warnings: [...(benchmark.warnings || [])],
  };
}
