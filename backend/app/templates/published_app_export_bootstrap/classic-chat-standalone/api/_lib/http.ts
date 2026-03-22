type CookieOptions = {
  httpOnly?: boolean;
  maxAge?: number;
  path?: string;
  sameSite?: "lax" | "strict" | "none";
  secure?: boolean;
};

export function json(value: unknown, init?: ResponseInit): Response {
  const headers = new Headers(init?.headers);
  if (!headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json; charset=utf-8");
  }
  return new Response(JSON.stringify(value), {
    ...init,
    headers,
  });
}

export function noContent(init?: ResponseInit): Response {
  return new Response(null, { ...init, status: init?.status ?? 204 });
}

export function parseCookies(request: Request): Record<string, string> {
  const raw = request.headers.get("cookie");
  if (!raw) {
    return {};
  }

  return Object.fromEntries(
    raw
      .split(";")
      .map((entry) => {
        const pivot = entry.indexOf("=");
        if (pivot < 0) {
          return [entry.trim(), ""];
        }
        return [
          decodeURIComponent(entry.slice(0, pivot).trim()),
          decodeURIComponent(entry.slice(pivot + 1).trim()),
        ];
      })
      .filter(([key]) => Boolean(key)),
  );
}

export function appendSetCookie(
  headers: Headers,
  name: string,
  value: string,
  options: CookieOptions = {},
): void {
  const parts = [`${encodeURIComponent(name)}=${encodeURIComponent(value)}`];
  parts.push(`Path=${options.path || "/"}`);

  if (typeof options.maxAge === "number") {
    parts.push(`Max-Age=${Math.max(0, Math.floor(options.maxAge))}`);
  }
  if (options.httpOnly !== false) {
    parts.push("HttpOnly");
  }
  if (options.sameSite) {
    parts.push(`SameSite=${options.sameSite}`);
  }
  if (options.secure) {
    parts.push("Secure");
  }

  headers.append("Set-Cookie", parts.join("; "));
}

export function appendExpiredCookie(headers: Headers, name: string, secure = false): void {
  appendSetCookie(headers, name, "", {
    httpOnly: true,
    maxAge: 0,
    path: "/",
    sameSite: "lax",
    secure,
  });
}

export function isSecureRequest(request: Request): boolean {
  const url = new URL(request.url);
  if (url.protocol === "https:") {
    return true;
  }

  return request.headers.get("x-forwarded-proto") === "https";
}

export function getPathParam(request: Request, prefix: string): string {
  const pathname = new URL(request.url).pathname;
  return decodeURIComponent(pathname.slice(prefix.length));
}
