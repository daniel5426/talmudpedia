import { spawnSync } from "node:child_process";

const isWindows = process.platform === "win32";
const command = isWindows ? "pnpm.cmd" : "pnpm";
const args = [
  "exec",
  "pagefind",
  "--site",
  ".next/server/app",
  "--output-path",
  "public/_pagefind",
];

const result = spawnSync(command, args, {
  cwd: process.cwd(),
  encoding: "utf8",
});

if (result.status === 0) {
  if (result.stdout) process.stdout.write(result.stdout);
  if (result.stderr) process.stderr.write(result.stderr);
  process.exit(0);
}

const output = `${result.stdout ?? ""}${result.stderr ?? ""}`;
const isUnsupportedPagefindArch =
  output.includes("not yet a supported architecture") &&
  output.includes("pagefind");

if (isUnsupportedPagefindArch) {
  console.warn(
    `Skipping Pagefind indexing on unsupported platform ${process.platform}-${process.arch}.`
  );
  if (output) process.stderr.write(output);
  process.exit(0);
}

if (result.stdout) process.stdout.write(result.stdout);
if (result.stderr) process.stderr.write(result.stderr);

process.exit(result.status ?? 1);
