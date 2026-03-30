import "dotenv/config";

const requiredEnvKeys = [
  "TALMUDPEDIA_BASE_URL",
  "TALMUDPEDIA_EMBED_API_KEY",
  "TALMUDPEDIA_AGENT_ID",
  "SESSION_COOKIE_SECRET",
] as const;

type RequiredEnvKey = (typeof requiredEnvKeys)[number];

export type StandaloneEnv = Record<RequiredEnvKey, string>;
export type SessionEnv = {
  SESSION_COOKIE_SECRET: string;
};

function requireEnv(key: string): string {
  const value = String(process.env[key] || "").trim();
  if (!value) {
    throw new Error(`Missing required environment variable: ${key}`);
  }
  return value;
}

let cachedEnv: StandaloneEnv | null = null;
let cachedSessionEnv: SessionEnv | null = null;

export function loadEnv(): StandaloneEnv {
  if (cachedEnv) {
    return cachedEnv;
  }

  cachedEnv = Object.fromEntries(
    requiredEnvKeys.map((key) => [key, requireEnv(key)]),
  ) as StandaloneEnv;
  return cachedEnv;
}

export function loadSessionEnv(): SessionEnv {
  if (cachedSessionEnv) {
    return cachedSessionEnv;
  }

  cachedSessionEnv = {
    SESSION_COOKIE_SECRET: requireEnv("SESSION_COOKIE_SECRET"),
  };

  return cachedSessionEnv;
}
