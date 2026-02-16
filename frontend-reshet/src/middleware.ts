import { NextRequest, NextResponse } from "next/server";

const APPS_BASE_DOMAIN = (process.env.NEXT_PUBLIC_APPS_BASE_DOMAIN || "apps.localhost").toLowerCase();
const APPS_HOST_RUNTIME_MODE = (
  process.env.NEXT_PUBLIC_APPS_HOST_RUNTIME_MODE ||
  (process.env.NODE_ENV === "development" ? "static_proxy" : "shell")
).toLowerCase();

function usesStaticProxyRuntimeMode(): boolean {
  return APPS_HOST_RUNTIME_MODE === "static_proxy" || APPS_HOST_RUNTIME_MODE === "static";
}

function shouldSkipPath(pathname: string): boolean {
  return (
    pathname.startsWith("/_next") ||
    pathname.startsWith("/api") ||
    pathname.startsWith("/favicon.ico") ||
    pathname.startsWith("/published") ||
    pathname.startsWith("/admin") ||
    pathname.startsWith("/auth") ||
    pathname.startsWith("/canva")
  );
}

export function middleware(request: NextRequest) {
  const hostHeader = (request.headers.get("host") || "").split(":")[0].toLowerCase();
  const { pathname } = request.nextUrl;

  if (!hostHeader || shouldSkipPath(pathname)) {
    return NextResponse.next();
  }

  if (!hostHeader.endsWith(`.${APPS_BASE_DOMAIN}`)) {
    return NextResponse.next();
  }

  const appSlug = hostHeader.slice(0, -(APPS_BASE_DOMAIN.length + 1));
  if (!appSlug) {
    return NextResponse.next();
  }

  const rewriteUrl = request.nextUrl.clone();
  if (usesStaticProxyRuntimeMode()) {
    rewriteUrl.pathname =
      pathname === "/"
        ? `/api/py/public/apps/${appSlug}/assets/index.html`
        : `/api/py/public/apps/${appSlug}/assets${pathname}`;
    return NextResponse.rewrite(rewriteUrl);
  }

  rewriteUrl.pathname = pathname === "/" ? `/published/${appSlug}` : `/published/${appSlug}${pathname}`;
  return NextResponse.rewrite(rewriteUrl);
}

export const config = {
  matcher: "/:path*",
};
