export type DemoClient = {
  id: string;
  name: string;
  sector: string;
  baseCurrency: string;
};

export type DemoDeal = {
  dealId: string;
  clientId: string;
  bank: string;
  currency: string;
  currencyPair: string;
  executionDate: string;
  notional: number;
  rate: number;
  productFamily: string;
  timeline: Array<{
    source: string;
    label: string;
    eventTime: string;
  }>;
  exposureTotal: number;
  sourceTablesUsed: string[];
};

export type DemoBenchmark = {
  currencyPair: string;
  date: string;
  source: string;
  rate: number;
  confidence: "high" | "medium" | "low";
  warnings?: string[];
};

export type PricoToolErrorCode =
  | "CLIENT_ID_REQUIRED"
  | "DEAL_ID_REQUIRED"
  | "CLIENT_NOT_FOUND"
  | "DEAL_NOT_FOUND"
  | "UNSUPPORTED_QUERY";

export class PricoToolError extends Error {
  readonly code: PricoToolErrorCode;
  readonly status: number;

  constructor(code: PricoToolErrorCode, message: string, status = 400) {
    super(message);
    this.code = code;
    this.status = status;
  }
}

export type BasePricoRequest = {
  client_id: string;
};

export type DateWindowRequest = BasePricoRequest & {
  date_from?: string;
  date_to?: string;
};

export type ClientActivitySummaryRequest = DateWindowRequest & {
  currencies?: string[];
};

export type ConcentrationRequest = DateWindowRequest;

export type DealScopedRequest = BasePricoRequest & {
  deal_id: string;
};

export type PricoSummaryMetricSet = {
  deal_count: number;
  total_notional_proxy: number;
  top_currencies: string[];
  top_banks: string[];
  activity_trend: string;
};

export type RecentDealRow = {
  deal_id: string;
  currency: string;
  bank: string;
  execution_date: string;
  notional: number;
  rate: number;
};

export type ConcentrationRow = {
  label: string;
  deal_count: number;
  notional_proxy: number;
  share_pct: number;
};

export type DealExplainerResponse = {
  deal: {
    deal_id: string;
    client_id: string;
    bank: string;
    currency: string;
    currency_pair: string;
    execution_date: string;
    rate: number;
    notional: number;
    product_family: string;
  };
  timeline: DemoDeal["timeline"];
  related_metrics: {
    exposure_total: number;
  };
  warnings: string[];
  source_tables_used: string[];
};

export type MarketContextResponse = {
  deal_context: {
    deal_id: string;
    client_id: string;
    currency_pair: string;
    deal_rate: number;
    deal_date: string;
  };
  benchmark: {
    source: string;
    benchmark_rate: number | null;
    confidence: "high" | "medium" | "low";
  };
  comparison: {
    delta: number | null;
    assessment: string;
  };
  warnings: string[];
};
