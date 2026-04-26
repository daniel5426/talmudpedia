export function normalizeAppsBuilderPreviewRoute(route: string): string | null {
  const trimmed = String(route || "").trim();
  if (!trimmed || trimmed.includes("${")) return null;
  const [pathname] = trimmed.split(/[?#]/);
  if (!pathname) return null;

  const normalized = pathname.startsWith("/") ? pathname : `/${pathname}`;
  const compact = normalized.replace(/\/{2,}/g, "/");
  const proxyMatch = compact.match(/^\/public\/apps-builder\/draft-dev\/sessions\/[^/]+\/preview(?:\/(.*))?$/);
  if (proxyMatch) {
    const resource = String(proxyMatch[1] || "").trim();
    if (!resource || resource === "/" || resource.startsWith("assets/") || resource.startsWith("_talmudpedia/")) {
      return "/";
    }
    return normalizeAppsBuilderPreviewRoute(`/${resource}`);
  }

  if (compact !== "/" && compact.endsWith("/")) {
    return compact.slice(0, -1) || "/";
  }
  return compact || "/";
}

function isAssetLikeRoute(route: string): boolean {
  if (!route || route === "/") return false;
  const lastSegment = route.split("/").filter(Boolean).pop() || "";
  return /\.[a-z0-9]{2,8}$/i.test(lastSegment);
}

function isRouteLiteralCandidate(value: string): boolean {
  const raw = String(value || "").trim();
  if (!raw) return true;
  if (raw.includes("${") || raw.startsWith("{")) return false;
  if (raw.startsWith("#") || raw.startsWith("?")) return false;
  if (raw.startsWith("./") || raw.startsWith("../")) return false;
  if (/^[a-z][a-z0-9+.-]*:/i.test(raw)) return false;
  return true;
}

function routeFromFilePath(filePath: string): string | null {
  const normalized = filePath.replace(/\\/g, "/");
  const appMatch = normalized.match(/(?:^|\/)(?:src\/)?app\/(.+)\/page\.(?:tsx|ts|jsx|js|mdx)$/);
  if (appMatch) {
    const segments = appMatch[1]
      .split("/")
      .filter(Boolean)
      .filter((segment) => !segment.startsWith("(") && !segment.startsWith("@"));
    if (segments.some((segment) => segment.startsWith("[") || segment.startsWith(":"))) {
      return null;
    }
    return normalizeAppsBuilderPreviewRoute(`/${segments.join("/")}`);
  }

  const pagesMatch = normalized.match(/(?:^|\/)(?:src\/)?pages\/(.+)\.(?:tsx|ts|jsx|js|mdx)$/);
  if (pagesMatch) {
    const relativePath = pagesMatch[1].replace(/\/index$/, "");
    if (!relativePath || relativePath === "index") {
      return "/";
    }
    if (relativePath.startsWith("api/")) {
      return null;
    }
    if (relativePath.split("/").some((segment) => segment.startsWith("[") || segment.startsWith(":"))) {
      return null;
    }
    return normalizeAppsBuilderPreviewRoute(`/${relativePath}`);
  }

  return null;
}

function addRoute(routes: Set<string>, candidate: string | null): void {
  if (!candidate || candidate.includes(":") || isAssetLikeRoute(candidate)) {
    return;
  }
  routes.add(candidate);
}

function addRouteLiteral(routes: Set<string>, value: string): void {
  if (!isRouteLiteralCandidate(value)) {
    return;
  }
  addRoute(routes, normalizeAppsBuilderPreviewRoute(value || "/"));
}

export function extractAppsBuilderPreviewRoutes(files: Record<string, string>): string[] {
  const routes = new Set<string>(["/"]);

  for (const [filePath, content] of Object.entries(files)) {
    addRoute(routes, routeFromFilePath(filePath));

    const routePatterns = [
      /\bpath\s*[=:]\s*["'`]([^"'`]*)["'`]/g,
      /\bnavigate\(\s*["'`]([^"'`]*)["'`]/g,
      /\b(?:href|to|pathname)\s*[:=]\s*["'`]([^"'`]*)["'`]/g,
    ];

    for (const pattern of routePatterns) {
      let match: RegExpExecArray | null;
      while ((match = pattern.exec(content)) !== null) {
        addRouteLiteral(routes, match[1]);
      }
    }
  }

  return Array.from(routes).sort((a, b) => {
    if (a === "/") return -1;
    if (b === "/") return 1;
    return a.localeCompare(b);
  });
}
