import clientsJson from "../../server/prico-demo/frozen_snapshot/json/prico.lekohot.json" with { type: "json" };

type FrozenClientRow = {
  mispar_lakoah?: number | string;
  shem_lakoah?: string;
  englishname?: string;
  laknpi?: string;
  sug_peilut?: string;
  matbea_ogen?: number | string;
};

export type DemoClient = {
  id: string;
  name: string;
  sector: string;
  baseCurrency: string;
};

const currencyCodeById: Record<string, string> = {
  "1": "USD",
  "5": "GBP",
  "6": "EUR",
  "40": "ILS",
};

function toDemoClient(row: FrozenClientRow): DemoClient | null {
  const id = String(row.mispar_lakoah ?? "").trim();
  const name =
    String(row.englishname ?? "").trim() ||
    String(row.laknpi ?? "").trim() ||
    String(row.shem_lakoah ?? "").trim();
  if (!id || !name) {
    return null;
  }

  const currencyId = String(row.matbea_ogen ?? "").trim();
  const sector = String(row.sug_peilut ?? "").trim() || "Unknown";
  const baseCurrency = currencyCodeById[currencyId] || "USD";

  return {
    id,
    name,
    sector,
    baseCurrency,
  };
}

const demoClients = (Array.isArray(clientsJson) ? clientsJson : [])
  .map((row) => toDemoClient(row as FrozenClientRow))
  .filter((row): row is DemoClient => row !== null)
  .sort((left, right) => left.id.localeCompare(right.id));

export function listDemoClients(): DemoClient[] {
  return demoClients;
}
