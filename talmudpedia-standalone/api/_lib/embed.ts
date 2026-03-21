import { EmbeddedAgentClient } from "@agents24/embed-sdk";

import { loadEnv } from "./env.js";

export const env = loadEnv();

export const embedClient = new EmbeddedAgentClient({
  baseUrl: env.TALMUDPEDIA_BASE_URL,
  apiKey: env.TALMUDPEDIA_EMBED_API_KEY,
});
