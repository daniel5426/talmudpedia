import clientsJson from "../../server/prico-demo/frozen_snapshot/prico/lekohot.json" with { type: "json" };

type FrozenClientRow = {
  mispar_lakoah?: number | string;
  shem_lakoah?: string;
};

export type DemoClient = {
  id: string;
  name: string;
  sector: string;
  baseCurrency: string;
};

const clientMetadataById: Record<string, Pick<DemoClient, "sector" | "baseCurrency">> = {
  "32001": { sector: "Food Imports", baseCurrency: "USD" },
  "32002": { sector: "MedTech", baseCurrency: "EUR" },
  "32003": { sector: "Retail", baseCurrency: "GBP" },
};

function toDemoClient(row: FrozenClientRow): DemoClient | null {
  const id = String(row.mispar_lakoah ?? "").trim();
  const name = String(row.shem_lakoah ?? "").trim();
  if (!id || !name) {
    return null;
  }

  const metadata = clientMetadataById[id] ?? {
    sector: "Unknown",
    baseCurrency: "USD",
  };

  return {
    id,
    name,
    sector: metadata.sector,
    baseCurrency: metadata.baseCurrency,
  };
}

const demoClients = (Array.isArray(clientsJson) ? clientsJson : [])
  .map((row) => toDemoClient(row as FrozenClientRow))
  .filter((row): row is DemoClient => row !== null);

export function listDemoClients(): DemoClient[] {
  return demoClients;
}
