import * as esbuild from "esbuild-wasm";

const ESBUILD_VERSION = "0.25.0";
const ESBUILD_WASM_URL = `https://unpkg.com/esbuild-wasm@${ESBUILD_VERSION}/esbuild.wasm`;

const GLOBAL_INIT_KEY = "__reactArtifactEsbuildInit";
type GlobalInitState = { promise: Promise<void> } | undefined;

const getGlobalInitState = () => {
  const globalScope = globalThis as typeof globalThis & {
    [GLOBAL_INIT_KEY]?: GlobalInitState;
  };
  return globalScope;
};

const ensureInitialized = async () => {
  const globalScope = getGlobalInitState();
  if (!globalScope[GLOBAL_INIT_KEY]) {
    globalScope[GLOBAL_INIT_KEY] = {
      promise: esbuild
        .initialize({
          wasmURL: ESBUILD_WASM_URL,
          worker: true,
        })
        .catch((error) => {
          const message = error instanceof Error ? error.message : "";
          if (message.includes("Cannot call \"initialize\" more than once")) {
            return;
          }
          throw error;
        }),
    };
  }
  await globalScope[GLOBAL_INIT_KEY]?.promise;
};

const CDN_ORIGIN = "https://esm.sh";
const REACT_VERSION = "19.2.0";

const ALLOWED_USER_IMPORTS: Record<string, string> = {
  react: `${CDN_ORIGIN}/react@${REACT_VERSION}`,
  "react-dom/client": `${CDN_ORIGIN}/react-dom@${REACT_VERSION}/client`,
  "react/jsx-runtime": `${CDN_ORIGIN}/react@${REACT_VERSION}/jsx-runtime`,
  "react/jsx-dev-runtime": `${CDN_ORIGIN}/react@${REACT_VERSION}/jsx-dev-runtime`,
};

const buildWrapper = () => {
  return `import React from "react";
import { createRoot } from "react-dom/client";
import * as AppModule from "virtual:app";

const App = AppModule.default ?? AppModule.App ?? AppModule;
const rootElement = document.getElementById("root");

if (!rootElement) {
  throw new Error("Preview root element not found.");
}

if (!App || (typeof App !== "function" && typeof App !== "object")) {
  throw new Error("No React component export found. Export default function App() { ... } or export const App = () => ...");
}

const root = createRoot(rootElement);
root.render(React.createElement(App));
`;
};

const normalizeVirtualPath = (path: string): string => {
  const cleaned = path.replace(/\\/g, "/").replace(/^\/+/, "");
  const parts: string[] = [];
  cleaned.split("/").forEach((part) => {
    if (!part || part === ".") return;
    if (part === "..") {
      parts.pop();
      return;
    }
    parts.push(part);
  });
  return parts.join("/");
};

const dirnameVirtualPath = (path: string): string => {
  const normalized = normalizeVirtualPath(path);
  const idx = normalized.lastIndexOf("/");
  if (idx <= 0) return "";
  return normalized.slice(0, idx);
};

const resolveLocalProjectPath = (
  importPath: string,
  importerPath: string,
  files: Record<string, string>,
): string | null => {
  const importerDir = dirnameVirtualPath(importerPath);
  const joined = normalizeVirtualPath(`${importerDir}/${importPath}`);
  const candidates = [
    joined,
    `${joined}.tsx`,
    `${joined}.ts`,
    `${joined}.jsx`,
    `${joined}.js`,
    `${joined}.css`,
    `${joined}/index.tsx`,
    `${joined}/index.ts`,
    `${joined}/index.jsx`,
    `${joined}/index.js`,
  ];
  for (const candidate of candidates) {
    if (files[candidate] !== undefined) {
      return candidate;
    }
  }
  return null;
};

const detectLoader = (path: string): esbuild.Loader => {
  if (path.endsWith(".ts")) return "ts";
  if (path.endsWith(".tsx")) return "tsx";
  if (path.endsWith(".jsx")) return "jsx";
  if (path.endsWith(".css")) return "css";
  return "js";
};

const buildFetchPlugin = (code: string): esbuild.Plugin => ({
  name: "react-artifact-fetch",
  setup(build) {
    build.onResolve({ filter: /^virtual:app$/ }, () => ({
      path: "virtual:app",
      namespace: "react-artifact-app",
    }));

    build.onResolve({ filter: /^https?:\/\// }, (args) => {
      if (args.namespace === "react-artifact-app") {
        return {
          errors: [{
            text: "Network imports are not allowed in React artifacts.",
          }],
        };
      }
      return {
        path: args.path,
        namespace: "react-artifact-http",
      };
    });

    build.onResolve({ filter: /^\// }, (args) => {
      if (args.importer && args.importer.startsWith(CDN_ORIGIN)) {
        return {
          path: `${CDN_ORIGIN}${args.path}`,
          namespace: "react-artifact-http",
        };
      }
      return {
        errors: [{
          text: "Absolute imports are not allowed in React artifacts.",
        }],
      };
    });

    build.onResolve({ filter: /^\./ }, (args) => {
      if (args.namespace === "react-artifact-app") {
        return {
          errors: [{
            text: "Relative imports are not allowed in React artifacts.",
          }],
        };
      }

      if (!args.importer) {
        return {
          errors: [{
            text: "Relative imports require a valid importer.",
          }],
        };
      }

      try {
        const resolved = new URL(args.path, args.importer).toString();
        return {
          path: resolved,
          namespace: "react-artifact-http",
        };
      } catch {
        return {
          errors: [{
            text: `Failed to resolve import: ${args.path}`,
          }],
        };
      }
    });

    build.onResolve({ filter: /^[^./].*/ }, (args) => {
      const pinned = ALLOWED_USER_IMPORTS[args.path];
      if (pinned) {
        return {
          path: pinned,
          namespace: "react-artifact-http",
        };
      }

      if (args.namespace === "react-artifact-app") {
        return {
          errors: [{
            text: `Only React imports are allowed. Unsupported import: ${args.path}`,
          }],
        };
      }

      return {
        path: `${CDN_ORIGIN}/${args.path}`,
        namespace: "react-artifact-http",
      };
    });

    build.onLoad({ filter: /.*/, namespace: "react-artifact-app" }, () => ({
      contents: code,
      loader: "tsx",
    }));

    const cache = new Map<string, { contents: string; resolveDir: string }>();

    build.onLoad({ filter: /.*/, namespace: "react-artifact-http" }, async (args) => {
      const cached = cache.get(args.path);
      if (cached) {
        return {
          contents: cached.contents,
          loader: "js",
          resolveDir: cached.resolveDir,
        };
      }

      const response = await fetch(args.path);
      if (!response.ok) {
        return {
          errors: [{
            text: `Failed to load dependency: ${args.path}`,
          }],
        };
      }

      const contents = await response.text();
      const url = new URL(args.path);
      const resolveDir = url.origin + url.pathname.slice(0, url.pathname.lastIndexOf("/") + 1);
      cache.set(args.path, { contents, resolveDir });

      return {
        contents,
        loader: "js",
        resolveDir,
      };
    });
  },
});

const buildProjectPlugin = (files: Record<string, string>, entryFile: string): esbuild.Plugin => {
  const normalizedEntry = normalizeVirtualPath(entryFile);
  const cache = new Map<string, { contents: string; resolveDir: string }>();

  return {
    name: "react-artifact-project",
    setup(build) {
      build.onResolve({ filter: /^virtual:project-entry$/ }, () => ({
        path: "virtual:project-entry",
        namespace: "react-artifact-project-entry",
      }));

      build.onLoad({ filter: /.*/, namespace: "react-artifact-project-entry" }, () => ({
        contents: `import "./${normalizedEntry}";`,
        loader: "ts",
      }));

      build.onResolve({ filter: /^https?:\/\// }, (args) => {
        if (args.namespace === "react-artifact-project") {
          return {
            errors: [{ text: "Network imports are not allowed in app builder projects." }],
          };
        }
        return { path: args.path, namespace: "react-artifact-http" };
      });

      build.onResolve({ filter: /^\// }, (args) => {
        if (args.importer && args.importer.startsWith(CDN_ORIGIN)) {
          return {
            path: `${CDN_ORIGIN}${args.path}`,
            namespace: "react-artifact-http",
          };
        }
        return {
          errors: [{ text: "Absolute imports are not allowed in app builder projects." }],
        };
      });

      build.onResolve({ filter: /^\./ }, (args) => {
        if (args.namespace === "react-artifact-http") {
          if (!args.importer) {
            return {
              errors: [{ text: "Relative CDN imports require a valid importer." }],
            };
          }

          try {
            const resolved = new URL(args.path, args.importer).toString();
            return {
              path: resolved,
              namespace: "react-artifact-http",
            };
          } catch {
            return {
              errors: [{ text: `Failed to resolve CDN import: ${args.path}` }],
            };
          }
        }

        const importer = args.namespace === "react-artifact-project-entry" ? "index.ts" : args.importer;
        const resolved = resolveLocalProjectPath(args.path, importer, files);
        if (!resolved) {
          return {
            errors: [{ text: `Could not resolve local import: ${args.path}` }],
          };
        }
        return {
          path: resolved,
          namespace: "react-artifact-project",
        };
      });

      build.onResolve({ filter: /^[^./].*/ }, (args) => {
        const pinned = ALLOWED_USER_IMPORTS[args.path];
        if (pinned) {
          return {
            path: pinned,
            namespace: "react-artifact-http",
          };
        }
        return {
          errors: [{ text: `Only React imports are allowed. Unsupported import: ${args.path}` }],
        };
      });

      build.onLoad({ filter: /.*/, namespace: "react-artifact-project" }, (args) => {
        const source = files[args.path];
        if (source === undefined) {
          return {
            errors: [{ text: `Missing source file: ${args.path}` }],
          };
        }
        return {
          contents: source,
          loader: detectLoader(args.path),
          resolveDir: dirnameVirtualPath(args.path),
        };
      });

      build.onLoad({ filter: /.*/, namespace: "react-artifact-http" }, async (args) => {
        const cached = cache.get(args.path);
        if (cached) {
          return {
            contents: cached.contents,
            loader: "js",
            resolveDir: cached.resolveDir,
          };
        }

        const response = await fetch(args.path);
        if (!response.ok) {
          return {
            errors: [{ text: `Failed to load dependency: ${args.path}` }],
          };
        }

        const contents = await response.text();
        const url = new URL(args.path);
        const resolveDir = url.origin + url.pathname.slice(0, url.pathname.lastIndexOf("/") + 1);
        cache.set(args.path, { contents, resolveDir });

        return {
          contents,
          loader: "js",
          resolveDir,
        };
      });
    },
  };
};

export type CompileResult =
  | { ok: true; output: string; css?: string }
  | { ok: false; error: string };

const normalizeBuildError = (error: unknown): CompileResult => {
  if (error && typeof error === "object" && "errors" in error) {
    const buildError = (error as { errors?: Array<{ text?: string; location?: { file?: string; line?: number; column?: number } }> }).errors?.[0];
    if (buildError?.text) {
      const location = buildError.location;
      const locationLabel = location?.line ? ` (line ${location.line}${location.column ? `:${location.column}` : ""})` : "";
      return { ok: false, error: `${buildError.text}${locationLabel}` };
    }
  }
  const message = error instanceof Error ? error.message : "Compilation failed.";
  return { ok: false, error: message };
};

export const compileReactArtifact = async (code: string): Promise<CompileResult> => {
  try {
    await ensureInitialized();
    const result = await esbuild.build({
      bundle: true,
      write: false,
      format: "iife",
      platform: "browser",
      target: ["es2020"],
      jsx: "automatic",
      plugins: [buildFetchPlugin(code)],
      stdin: {
        contents: buildWrapper(),
        loader: "tsx",
        resolveDir: "/",
      },
    });

    const output = result.outputFiles?.[0]?.text;
    if (!output) {
      return { ok: false, error: "Build produced no output." };
    }

    const css = result.outputFiles
      ?.filter((file) => file.path.endsWith(".css"))
      .map((file) => file.text)
      .join("\n");

    return { ok: true, output, css: css || undefined };
  } catch (error) {
    return normalizeBuildError(error);
  }
};

export const compileReactArtifactProject = async (
  files: Record<string, string>,
  entryFile: string,
): Promise<CompileResult> => {
  try {
    await ensureInitialized();
    const normalizedEntry = normalizeVirtualPath(entryFile);
    if (!files[normalizedEntry]) {
      return { ok: false, error: `Entry file not found: ${entryFile}` };
    }

    const result = await esbuild.build({
      bundle: true,
      write: false,
      outdir: "out",
      format: "iife",
      platform: "browser",
      target: ["es2020"],
      jsx: "automatic",
      plugins: [buildProjectPlugin(files, normalizedEntry)],
      stdin: {
        contents: "import \"virtual:project-entry\";",
        loader: "ts",
        resolveDir: "/",
      },
    });

    const jsOutputFile = result.outputFiles?.find((file) => file.path.endsWith(".js"));
    const output = jsOutputFile?.text || result.outputFiles?.[0]?.text;
    if (!output) {
      return { ok: false, error: "Build produced no output." };
    }

    const css = result.outputFiles
      ?.filter((file) => file.path.endsWith(".css"))
      .map((file) => file.text)
      .join("\n");

    return { ok: true, output, css: css || undefined };
  } catch (error) {
    return normalizeBuildError(error);
  }
};
