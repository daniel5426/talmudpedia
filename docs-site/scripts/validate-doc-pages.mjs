import fs from "node:fs";
import path from "node:path";
import matter from "gray-matter";

const root = path.resolve("app");
const requiredFields = [
  "title",
  "description",
  "status",
  "audience",
  "lastUpdated",
  "lastValidated",
  "canonicalSources",
  "verificationStatus"
];
const allowedStatus = new Set(["draft", "published"]);
const allowedVerificationStatus = new Set(["not-run", "partial", "validated"]);

function walk(dir) {
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  return entries.flatMap((entry) => {
    const resolved = path.join(dir, entry.name);
    if (entry.isDirectory()) return walk(resolved);
    if (entry.name === "page.mdx") return [resolved];
    return [];
  });
}

const pages = walk(root);
const failures = [];

for (const file of pages) {
  const source = fs.readFileSync(file, "utf8");
  const { data } = matter(source);

  for (const field of requiredFields) {
    if (!(field in data)) {
      failures.push(`${file}: missing frontmatter field "${field}"`);
    }
  }

  if (data.status && !allowedStatus.has(data.status)) {
    failures.push(`${file}: invalid status "${data.status}"`);
  }

  if (
    data.verificationStatus &&
    !allowedVerificationStatus.has(data.verificationStatus)
  ) {
    failures.push(
      `${file}: invalid verificationStatus "${data.verificationStatus}"`
    );
  }

  if (data.canonicalSources && !Array.isArray(data.canonicalSources)) {
    failures.push(`${file}: canonicalSources must be an array`);
  }
}

if (failures.length > 0) {
  console.error("Docs content validation failed:");
  for (const failure of failures) {
    console.error(`- ${failure}`);
  }
  process.exit(1);
}

console.log(`Validated ${pages.length} docs pages.`);
