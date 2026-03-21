import { handleMarketContext } from "../_lib/prico-tools.js";

export async function POST(request: Request): Promise<Response> {
  return handleMarketContext(request);
}
