import "dotenv/config";

const requiredEnvKeys = [
  "TALMUDPEDIA_BASE_URL",
  "TALMUDPEDIA_EMBED_API_KEY",
  "TALMUDPEDIA_AGENT_ID",
  "SESSION_COOKIE_SECRET",
] as const;

type RequiredEnvKey = (typeof requiredEnvKeys)[number];

export type StandaloneEnv = Record<RequiredEnvKey, string>;

function requireEnv(key: RequiredEnvKey): string {
  const value = String(process.env[key] || "").trim();
  if (!value) {
    throw new Error(`Missing required environment variable: ${key}`);
  }
  return value;
}

let cachedEnv: StandaloneEnv | null = null;

export function loadEnv(): StandaloneEnv {
  if (cachedEnv) {
    return cachedEnv;
  }
  cachedEnv = Object.fromEntries(
    requiredEnvKeys.map((key) => [key, requireEnv(key)]),
  ) as StandaloneEnv;
  return cachedEnv;
}
