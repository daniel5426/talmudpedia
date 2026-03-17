import { cp, mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const packageRoot = path.resolve(__dirname, "..");
const fixtureRoot = path.join(packageRoot, "fixtures", "smoke-consumer");

function run(command, args, cwd) {
  const result = spawnSync(command, args, {
    cwd,
    encoding: "utf8",
    stdio: "pipe",
  });
  if (result.status !== 0) {
    const stderr = result.stderr?.trim();
    const stdout = result.stdout?.trim();
    throw new Error(
      [`Command failed: ${command} ${args.join(" ")}`, stdout, stderr].filter(Boolean).join("\n\n"),
    );
  }
  return result.stdout.trim();
}

async function main() {
  const packOutput = run("npm", ["pack", "--json", "--ignore-scripts"], packageRoot);
  const [{ filename }] = JSON.parse(packOutput);
  const tarballPath = path.join(packageRoot, filename);
  const tempRoot = await mkdtemp(path.join(os.tmpdir(), "talmudpedia-embed-sdk-"));

  try {
    await cp(fixtureRoot, tempRoot, { recursive: true });
    run("npm", ["install", tarballPath], tempRoot);
    run("npm", ["run", "verify"], tempRoot);
  } finally {
    await rm(tarballPath, { force: true });
    await rm(tempRoot, { recursive: true, force: true });
  }
}

await main();
