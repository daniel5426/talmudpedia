import type {
  ClientActivitySummaryRequest,
  ConcentrationRequest,
  DealExplainerResponse,
  DealScopedRequest,
  MarketContextResponse,
  PricoSummaryMetricSet,
  RecentDealRow,
} from "./contracts.js";
import { PricoToolError } from "./contracts.js";
import { querySql } from "./sql.js";

type DemoClientRecord = {
  id: string;
  name: string;
  sector: string;
  baseCurrency: string;
};

type DealRow = {
  deal_id: string;
  client_id: string;
  client_name: string;
  bank_name: string;
  execution_date_raw: string;
  product_code: string;
  spot: string;
  swap_rate: string;
  final_rate: string;
  commission_rate: string;
  commission_amount: string;
  primary_currency: string;
  secondary_currency: string;
  has_paku: string;
  has_nigrarot: string;
  has_ssars: string;
};

type BenchmarkRow = {
  PairName: string;
  BidAskAverage: string;
  LastCloseValue: string;
  LastDate: string;
};

const LIVE_PRICO_CLIENTS: DemoClientRecord[] = [
  { id: "32001", name: "Orion Foods", sector: "Food Imports", baseCurrency: "USD" },
  { id: "32002", name: "Atlas Medical", sector: "MedTech", baseCurrency: "EUR" },
  { id: "32003", name: "Cedar Mobility", sector: "Retail", baseCurrency: "GBP" },
];

function requireClient(clientId: string): DemoClientRecord {
  const normalized = String(clientId || "").trim();
  if (!normalized) {
    throw new PricoToolError("CLIENT_ID_REQUIRED", "client_id is required.", 400);
  }
  const client = LIVE_PRICO_CLIENTS.find((item) => item.id === normalized);
  if (!client) {
    throw new PricoToolError("CLIENT_NOT_FOUND", `Unknown PRICO client '${normalized}'.`, 404);
  }
  return client;
}

function requireDealId(dealId: string): string {
  const normalized = String(dealId || "").trim();
  if (!normalized) {
    throw new PricoToolError("DEAL_ID_REQUIRED", "deal_id is required.", 400);
  }
  if (!/^\d+$/.test(normalized)) {
    throw new PricoToolError("DEAL_ID_REQUIRED", "deal_id must be numeric.", 400);
  }
  return normalized;
}

function normalizeDateKey(value?: string): string | null {
  const normalized = String(value || "").trim();
  if (!normalized) {
    return null;
  }
  if (!/^\d{4}-\d{2}-\d{2}$/.test(normalized)) {
    throw new PricoToolError("UNSUPPORTED_QUERY", `Invalid ISO date '${normalized}'.`, 400);
  }
  return normalized.replaceAll("-", "");
}

function formatDateKey(value: string): string {
  const raw = String(value || "").trim();
  if (/^\d{8}$/.test(raw)) {
    return `${raw.slice(0, 4)}-${raw.slice(4, 6)}-${raw.slice(6, 8)}`;
  }
  return raw;
}

function toNumber(value: string): number {
  const normalized = String(value || "").trim();
  if (!normalized) {
    return 0;
  }
  const parsed = Number(normalized);
  return Number.isFinite(parsed) ? parsed : 0;
}

function cleanLabel(value: string, fallback: string): string {
  const normalized = String(value || "").trim();
  return normalized || fallback;
}

function escapeSqlString(value: string): string {
  return value.replaceAll("'", "''");
}

function normalizeCurrencyList(currencies?: string[]): string[] {
  const items = Array.isArray(currencies) ? currencies : [];
  return items
    .map((value) => String(value || "").trim().toUpperCase())
    .filter((value) => /^[A-Z]{3,10}$/.test(value));
}

function buildWhereClause(payload: ClientActivitySummaryRequest | ConcentrationRequest): string {
  const conditions = [`i.lakoah_mispar = ${Number(requireClient(payload.client_id).id)}`];
  const dateFrom = normalizeDateKey(payload.date_from);
  const dateTo = normalizeDateKey(payload.date_to);
  if (dateFrom) {
    conditions.push(`i.taharich_bitzua >= '${dateFrom}'`);
  }
  if (dateTo) {
    conditions.push(`i.taharich_bitzua <= '${dateTo}'`);
  }
  const currencies = normalizeCurrencyList(
    "currencies" in payload ? payload.currencies : undefined,
  );
  if (currencies.length > 0) {
    const list = currencies.map((value) => `'${escapeSqlString(value)}'`).join(", ");
    conditions.push(`UPPER(LTRIM(RTRIM(COALESCE(m1.teur_matbea, '')))) IN (${list})`);
  }
  return conditions.join(" AND ");
}

function deriveNotionalProxy(row: DealRow): number {
  const commissionAmount = Math.abs(toNumber(row.commission_amount));
  const commissionRate = Math.abs(toNumber(row.commission_rate));
  if (commissionAmount > 0 && commissionRate > 0) {
    return Math.round((commissionAmount / commissionRate) * 10);
  }
  return 0;
}

function resolveDealRate(row: DealRow): number {
  const finalRate = toNumber(row.final_rate);
  if (finalRate > 0) {
    return finalRate;
  }
  const spot = toNumber(row.spot);
  if (spot > 0) {
    return spot;
  }
  return 0;
}

function resolveCurrency(row: DealRow): { currency: string; pair: string | null } {
  const primary = cleanLabel(row.primary_currency, "");
  const secondary = cleanLabel(row.secondary_currency, "");
  if (primary && secondary) {
    return {
      currency: primary,
      pair: `${primary}/${secondary}`,
    };
  }
  if (primary) {
    return { currency: primary, pair: null };
  }
  return { currency: "UNKNOWN", pair: null };
}

function summarizeTrend(rows: DealRow[]): string {
  if (rows.length === 0) return "no_recent_activity";
  const counts = new Map<string, number>();
  for (const row of rows) {
    const date = formatDateKey(row.execution_date_raw);
    counts.set(date, (counts.get(date) || 0) + 1);
  }
  const top = [...counts.entries()].sort((left, right) => right[1] - left[1])[0];
  if (!top) return "no_recent_activity";
  return top[1] > 1 ? `clustered_on_${top[0]}` : `steady_activity_through_${top[0]}`;
}

function topLabels(rows: DealRow[], pick: (row: DealRow) => string): string[] {
  const counts = new Map<string, number>();
  for (const row of rows) {
    const label = pick(row);
    counts.set(label, (counts.get(label) || 0) + 1);
  }
  return [...counts.entries()]
    .sort((left, right) => right[1] - left[1])
    .slice(0, 3)
    .map(([label]) => label);
}

function productFamily(productCode: string): string {
  const code = Number(productCode);
  if (code === 4) return "Forward";
  if (code === 6) return "Spot";
  if (code === 8 || code === 18) return "Option";
  return `Product ${String(productCode || "").trim() || "Unknown"}`;
}

async function getDealsForClient(
  payload: ClientActivitySummaryRequest | ConcentrationRequest,
): Promise<DealRow[]> {
  const whereClause = buildWhereClause(payload);
  return querySql<DealRow>(`
SET NOCOUNT ON;
SELECT
  CAST(i.ishur_iska AS varchar(32)) AS deal_id,
  CAST(i.lakoah_mispar AS varchar(32)) AS client_id,
  LTRIM(RTRIM(COALESCE(l.shem_lakoah, ''))) AS client_name,
  LTRIM(RTRIM(COALESCE(NULLIF(b.teur_bank, ''), CONCAT('Bank ', CAST(i.mispar_bank AS varchar(32)))))) AS bank_name,
  i.taharich_bitzua AS execution_date_raw,
  CAST(i.sug_iska AS varchar(32)) AS product_code,
  CAST(i.spot AS varchar(64)) AS spot,
  CAST(i.svop AS varchar(64)) AS swap_rate,
  CAST(i.shahar_sofi AS varchar(64)) AS final_rate,
  CAST(i.sheur_amlat_lakoah AS varchar(64)) AS commission_rate,
  CAST(i.amlat_lakoah AS varchar(64)) AS commission_amount,
  LTRIM(RTRIM(COALESCE(m1.teur_matbea, ''))) AS primary_currency,
  LTRIM(RTRIM(COALESCE(m2.teur_matbea, ''))) AS secondary_currency,
  CASE WHEN p.iska IS NULL THEN '0' ELSE '1' END AS has_paku,
  CASE WHEN nb.ishur_iska IS NULL THEN '0' ELSE '1' END AS has_nigrarot,
  CASE WHEN s.iska IS NULL THEN '0' ELSE '1' END AS has_ssars
FROM prico.iskaot i
LEFT JOIN prico.lekohot l
  ON l.mispar_lakoah = i.lakoah_mispar
LEFT JOIN prico.bankim b
  ON b.mispar_bank = i.mispar_bank
LEFT JOIN prico.nigrarot_bankaiyot nb
  ON nb.ishur_iska = i.ishur_iska
LEFT JOIN prico.matbeot m1
  ON m1.mispar_matbea = nb.code_matbea_1_1
LEFT JOIN prico.matbeot m2
  ON m2.mispar_matbea = nb.code_matbea_1_2
LEFT JOIN prico.paku p
  ON p.iska = i.ishur_iska
LEFT JOIN prico.ssars s
  ON s.iska = i.ishur_iska
WHERE ${whereClause}
ORDER BY i.taharich_bitzua DESC, i.ishur_iska DESC
`);
}

async function getDealForClient(clientId: string, dealId: string): Promise<DealRow> {
  const dealRows = await querySql<DealRow>(`
SET NOCOUNT ON;
SELECT TOP 1
  CAST(i.ishur_iska AS varchar(32)) AS deal_id,
  CAST(i.lakoah_mispar AS varchar(32)) AS client_id,
  LTRIM(RTRIM(COALESCE(l.shem_lakoah, ''))) AS client_name,
  LTRIM(RTRIM(COALESCE(NULLIF(b.teur_bank, ''), CONCAT('Bank ', CAST(i.mispar_bank AS varchar(32)))))) AS bank_name,
  i.taharich_bitzua AS execution_date_raw,
  CAST(i.sug_iska AS varchar(32)) AS product_code,
  CAST(i.spot AS varchar(64)) AS spot,
  CAST(i.svop AS varchar(64)) AS swap_rate,
  CAST(i.shahar_sofi AS varchar(64)) AS final_rate,
  CAST(i.sheur_amlat_lakoah AS varchar(64)) AS commission_rate,
  CAST(i.amlat_lakoah AS varchar(64)) AS commission_amount,
  LTRIM(RTRIM(COALESCE(m1.teur_matbea, ''))) AS primary_currency,
  LTRIM(RTRIM(COALESCE(m2.teur_matbea, ''))) AS secondary_currency,
  CASE WHEN p.iska IS NULL THEN '0' ELSE '1' END AS has_paku,
  CASE WHEN nb.ishur_iska IS NULL THEN '0' ELSE '1' END AS has_nigrarot,
  CASE WHEN s.iska IS NULL THEN '0' ELSE '1' END AS has_ssars
FROM prico.iskaot i
LEFT JOIN prico.lekohot l
  ON l.mispar_lakoah = i.lakoah_mispar
LEFT JOIN prico.bankim b
  ON b.mispar_bank = i.mispar_bank
LEFT JOIN prico.nigrarot_bankaiyot nb
  ON nb.ishur_iska = i.ishur_iska
LEFT JOIN prico.matbeot m1
  ON m1.mispar_matbea = nb.code_matbea_1_1
LEFT JOIN prico.matbeot m2
  ON m2.mispar_matbea = nb.code_matbea_1_2
LEFT JOIN prico.paku p
  ON p.iska = i.ishur_iska
LEFT JOIN prico.ssars s
  ON s.iska = i.ishur_iska
WHERE i.lakoah_mispar = ${Number(clientId)} AND i.ishur_iska = ${Number(dealId)}
ORDER BY i.ishur_iska DESC
`);
  const deal = dealRows[0];
  if (!deal) {
    throw new PricoToolError(
      "DEAL_NOT_FOUND",
      `Deal '${dealId}' was not found for client '${clientId}'.`,
      404,
    );
  }
  return deal;
}

async function getBenchmarkForPair(pairName: string, dateKey: string): Promise<BenchmarkRow | null> {
  const rows = await querySql<BenchmarkRow>(`
SET NOCOUNT ON;
SELECT TOP 1
  PairName,
  CAST(BidAskAverage AS varchar(64)) AS BidAskAverage,
  CAST(LastCloseValue AS varchar(64)) AS LastCloseValue,
  LastDate
FROM dbo.CurrencyPairsHistory
WHERE PairName = '${escapeSqlString(pairName)}' AND LastDate = '${dateKey}'
ORDER BY LastDate DESC
`);
  return rows[0] || null;
}

export function listDemoClients(): DemoClientRecord[] {
  return LIVE_PRICO_CLIENTS;
}

export async function getClientActivitySummary(payload: ClientActivitySummaryRequest) {
  const client = requireClient(payload.client_id);
  const currencies = normalizeCurrencyList(payload.currencies);
  const deals = await getDealsForClient(payload);

  const summary: PricoSummaryMetricSet = {
    deal_count: deals.length,
    total_notional_proxy: deals.reduce((sum, row) => sum + deriveNotionalProxy(row), 0),
    top_currencies: topLabels(deals, (row) => resolveCurrency(row).currency),
    top_banks: topLabels(deals, (row) => cleanLabel(row.bank_name, `Bank ${row.deal_id}`)),
    activity_trend: summarizeTrend(deals),
  };

  const recentDeals: RecentDealRow[] = deals.slice(0, 8).map((row) => ({
    deal_id: row.deal_id,
    currency: resolveCurrency(row).currency,
    bank: cleanLabel(row.bank_name, `Bank ${row.deal_id}`),
    execution_date: formatDateKey(row.execution_date_raw),
    notional: deriveNotionalProxy(row),
    rate: resolveDealRate(row),
  }));

  const dataQualityNotes: string[] = [];
  if (deals.length === 0) {
    dataQualityNotes.push("No deals matched the current live date/currency filter.");
  } else {
    dataQualityNotes.push(
      "notional_proxy is derived from customer commission fields because direct principal values are sparse in the current live rows.",
    );
  }

  return {
    client: {
      client_id: client.id,
      client_name: cleanLabel(deals[0]?.client_name || client.name, client.name),
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
    data_quality_notes: dataQualityNotes,
    source_tables_used: [
      "prico.iskaot",
      "prico.bankim",
      "prico.lekohot",
      "prico.nigrarot_bankaiyot",
      "prico.paku",
      "prico.ssars",
    ],
  };
}

function concentrationRows(
  deals: DealRow[],
  pick: (row: DealRow) => string,
): Array<{
  label: string;
  deal_count: number;
  notional_proxy: number;
  share_pct: number;
}> {
  const total = deals.reduce((sum, row) => sum + deriveNotionalProxy(row), 0);
  const buckets = new Map<string, { dealCount: number; notionalProxy: number }>();
  for (const row of deals) {
    const label = pick(row);
    const bucket = buckets.get(label) || { dealCount: 0, notionalProxy: 0 };
    bucket.dealCount += 1;
    bucket.notionalProxy += deriveNotionalProxy(row);
    buckets.set(label, bucket);
  }
  return [...buckets.entries()]
    .map(([label, bucket]) => ({
      label,
      deal_count: bucket.dealCount,
      notional_proxy: bucket.notionalProxy,
      share_pct: total > 0 ? Number(((bucket.notionalProxy / total) * 100).toFixed(1)) : 0,
    }))
    .sort((left, right) => right.notional_proxy - left.notional_proxy);
}

export async function getBankConcentration(payload: ConcentrationRequest) {
  const client = requireClient(payload.client_id);
  const deals = await getDealsForClient(payload);
  const rows = concentrationRows(deals, (row) => cleanLabel(row.bank_name, "Unknown bank")).map(
    (row) => ({
      bank: row.label,
      deal_count: row.deal_count,
      notional_proxy: row.notional_proxy,
      share_pct: row.share_pct,
    }),
  );

  return {
    client: {
      client_id: client.id,
      client_name: cleanLabel(deals[0]?.client_name || client.name, client.name),
    },
    rows,
    risk_flags:
      rows.length > 0 && rows[0].share_pct >= 60
        ? [`${rows[0].bank} concentration is above the live demo threshold.`]
        : [],
    filters_used: {
      client_id: client.id,
      date_from: payload.date_from || null,
      date_to: payload.date_to || null,
    },
    data_quality_notes:
      rows.length === 0
        ? ["No bank concentration rows were available for the selected live window."]
        : [
            "notional_proxy is derived from customer commission fields because direct principal values are sparse in the current live rows.",
          ],
    source_tables_used: ["prico.iskaot", "prico.bankim", "prico.lekohot"],
  };
}

export async function getCurrencyConcentration(payload: ConcentrationRequest) {
  const client = requireClient(payload.client_id);
  const deals = await getDealsForClient(payload);
  const rows = concentrationRows(deals, (row) => resolveCurrency(row).currency).map((row) => ({
    currency: row.label,
    deal_count: row.deal_count,
    notional_proxy: row.notional_proxy,
    share_pct: row.share_pct,
  }));

  return {
    client: {
      client_id: client.id,
      client_name: cleanLabel(deals[0]?.client_name || client.name, client.name),
    },
    rows,
    risk_flags:
      rows.length > 0 && rows[0].share_pct >= 65
        ? [`${rows[0].currency} dominates recent live activity for this client.`]
        : [],
    filters_used: {
      client_id: client.id,
      date_from: payload.date_from || null,
      date_to: payload.date_to || null,
    },
    data_quality_notes:
      rows.length === 0
        ? ["No currency concentration rows were available for the selected live window."]
        : [
            "currency mapping currently prefers nigrarot_bankaiyot live rows when available.",
            "notional_proxy is derived from customer commission fields because direct principal values are sparse in the current live rows.",
          ],
    source_tables_used: ["prico.iskaot", "prico.matbeot", "prico.nigrarot_bankaiyot"],
  };
}

export async function getDealExplainer(payload: DealScopedRequest): Promise<DealExplainerResponse> {
  const client = requireClient(payload.client_id);
  const dealId = requireDealId(payload.deal_id);
  const deal = await getDealForClient(client.id, dealId);
  const resolvedCurrency = resolveCurrency(deal);
  const timeline = [
    {
      source: "prico.iskaot",
      label: "Deal row recorded",
      eventTime: `${formatDateKey(deal.execution_date_raw)}T00:00:00Z`,
    },
    ...(deal.has_paku === "1"
      ? [
          {
            source: "prico.paku",
            label: "Operational follow-up row found",
            eventTime: `${formatDateKey(deal.execution_date_raw)}T00:00:00Z`,
          },
        ]
      : []),
    ...(deal.has_nigrarot === "1"
      ? [
          {
            source: "prico.nigrarot_bankaiyot",
            label: "Derivative profile row found",
            eventTime: `${formatDateKey(deal.execution_date_raw)}T00:00:00Z`,
          },
        ]
      : []),
    ...(deal.has_ssars === "1"
      ? [
          {
            source: "prico.ssars",
            label: "Secondary status row found",
            eventTime: `${formatDateKey(deal.execution_date_raw)}T00:00:00Z`,
          },
        ]
      : []),
  ];

  const warnings: string[] = [];
  if (timeline.length < 2) {
    warnings.push("Related post-deal live timeline data is sparse for this deal.");
  }
  warnings.push(
    "exposure_total is currently a proxy derived from customer commission fields because direct principal values are sparse in the current live rows.",
  );

  return {
    deal: {
      deal_id: deal.deal_id,
      client_id: client.id,
      bank: cleanLabel(deal.bank_name, "Unknown bank"),
      currency: resolvedCurrency.currency,
      currency_pair: resolvedCurrency.pair || `${resolvedCurrency.currency}/UNKNOWN`,
      execution_date: formatDateKey(deal.execution_date_raw),
      rate: resolveDealRate(deal),
      notional: deriveNotionalProxy(deal),
      product_family: productFamily(deal.product_code),
    },
    timeline,
    related_metrics: {
      exposure_total: deriveNotionalProxy(deal),
    },
    warnings,
    source_tables_used: [
      "prico.iskaot",
      "prico.bankim",
      "prico.lekohot",
      ...(deal.has_nigrarot === "1" ? ["prico.nigrarot_bankaiyot"] : []),
      ...(deal.has_paku === "1" ? ["prico.paku"] : []),
      ...(deal.has_ssars === "1" ? ["prico.ssars"] : []),
    ],
  };
}

export async function getMarketContext(payload: DealScopedRequest): Promise<MarketContextResponse> {
  const client = requireClient(payload.client_id);
  const dealId = requireDealId(payload.deal_id);
  const deal = await getDealForClient(client.id, dealId);
  const resolvedCurrency = resolveCurrency(deal);
  const executionDate = formatDateKey(deal.execution_date_raw);

  if (!resolvedCurrency.pair) {
    return {
      deal_context: {
        deal_id: deal.deal_id,
        client_id: client.id,
        currency_pair: `${resolvedCurrency.currency}/UNKNOWN`,
        deal_rate: resolveDealRate(deal),
        deal_date: executionDate,
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
      warnings: ["No benchmark pair mapping was available for this deal in the live dataset."],
    };
  }

  const benchmark = await getBenchmarkForPair(
    resolvedCurrency.pair,
    String(deal.execution_date_raw || "").trim(),
  );
  if (!benchmark) {
    return {
      deal_context: {
        deal_id: deal.deal_id,
        client_id: client.id,
        currency_pair: resolvedCurrency.pair,
        deal_rate: resolveDealRate(deal),
        deal_date: executionDate,
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
      warnings: [
        `No CurrencyPairsHistory benchmark row was available for ${resolvedCurrency.pair} on ${executionDate}.`,
      ],
    };
  }

  const benchmarkRate = toNumber(benchmark.BidAskAverage) || toNumber(benchmark.LastCloseValue);
  const delta = Number((resolveDealRate(deal) - benchmarkRate).toFixed(4));
  let assessment = "within_normal_range";
  if (Math.abs(delta) >= 0.05) {
    assessment = "materially_different";
  } else if (Math.abs(delta) >= 0.02) {
    assessment = "slightly_different";
  }

  return {
    deal_context: {
      deal_id: deal.deal_id,
      client_id: client.id,
      currency_pair: resolvedCurrency.pair,
      deal_rate: resolveDealRate(deal),
      deal_date: executionDate,
    },
    benchmark: {
      source: "dbo.CurrencyPairsHistory",
      benchmark_rate: benchmarkRate,
      confidence: "high",
    },
    comparison: {
      delta,
      assessment,
    },
    warnings: [],
  };
}
