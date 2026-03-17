const requiredEnvKeys = [
  "TALMUDPEDIA_BASE_URL",
  "TALMUDPEDIA_EMBED_API_KEY",
  "TALMUDPEDIA_AGENT_ID",
  "SESSION_COOKIE_SECRET",
] as const;

type RequiredEnvKey = (typeof requiredEnvKeys)[number];

type StandaloneEnv = Record<RequiredEnvKey, string> & {
  PORT: number;
};

function requireEnv(key: RequiredEnvKey): string {
  const value = String(process.env[key] || "").trim();
  if (!value) {
    throw new Error(`Missing required environment variable: ${key}`);
  }
  return value;
}

export function loadEnv(): StandaloneEnv {
  const env = Object.fromEntries(
    requiredEnvKeys.map((key) => [key, requireEnv(key)]),
  ) as Record<RequiredEnvKey, string>;

  const port = Number(process.env.PORT || 3001);
  if (!Number.isFinite(port) || port < 1) {
    throw new Error("PORT must be a positive integer.");
  }

  return {
    ...env,
    PORT: port,
  };
}
