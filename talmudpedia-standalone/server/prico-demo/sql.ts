import { execFile } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

const moduleDir = dirname(fileURLToPath(import.meta.url));
const queryScriptPath = join(moduleDir, "query_sql.py");

function requireEnv(key: string, fallback?: string): string {
  const value = String(process.env[key] || fallback || "").trim();
  if (!value) {
    throw new Error(`Missing required environment variable: ${key}`);
  }
  return value;
}

function getSqlConfig() {
  return {
    host: requireEnv("PRICO_DB_HOST", "127.0.0.1"),
    port: requireEnv("PRICO_DB_PORT", "1433"),
    user: requireEnv("PRICO_DB_USER", "ui_test"),
    password: requireEnv("PRICO_DB_PASSWORD", "UiTest12345"),
    database: requireEnv("PRICO_DB_DATABASE", "PricoDBForAI"),
  };
}

export type SqlRow = Record<string, unknown>;

export async function querySql<T extends SqlRow = SqlRow>(query: string): Promise<T[]> {
  const config = getSqlConfig();
  const { stdout, stderr } = await execFileAsync(
    "python3",
    [queryScriptPath, query],
    {
      env: {
        ...process.env,
        PRICO_DB_HOST: config.host,
        PRICO_DB_PORT: config.port,
        PRICO_DB_USER: config.user,
        PRICO_DB_PASSWORD: config.password,
        PRICO_DB_DATABASE: config.database,
      },
      maxBuffer: 1024 * 1024 * 8,
    },
  );

  if (stderr && String(stderr).trim()) {
    throw new Error(String(stderr).trim());
  }

  const text = String(stdout || "").trim();
  if (!text) {
    return [];
  }

  return JSON.parse(text) as T[];
}
