import { createHmac, randomUUID } from "node:crypto";

import {
  appendExpiredCookie,
  appendSetCookie,
  isSecureRequest,
  parseCookies,
} from "./http.js";

const SESSION_COOKIE_NAME = "tp_standalone_session";
const SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 30;

export type SessionInfo = {
  user: {
    id: string;
    email: string;
    full_name: string;
    avatar: string | null;
  };
};

function signValue(value: string, secret: string): string {
  return createHmac("sha256", secret).update(value).digest("hex");
}

function serializeSessionValue(userId: string, secret: string): string {
  return `${userId}.${signValue(userId, secret)}`;
}

function parseSignedSession(raw: string | undefined, secret: string): string | null {
  const value = String(raw || "").trim();
  if (!value) {
    return null;
  }
  const pivot = value.lastIndexOf(".");
  if (pivot <= 0) {
    return null;
  }
  const userId = value.slice(0, pivot);
  const signature = value.slice(pivot + 1);
  return signValue(userId, secret) === signature ? userId : null;
}

function buildUser(userId: string) {
  const suffix = userId.slice(-8).toUpperCase();
  return {
    id: userId,
    email: `local-${suffix.toLowerCase()}@example.local`,
    full_name: `Local User ${suffix}`,
    avatar: null,
  };
}

export function ensureSession(
  request: Request,
  responseHeaders: Headers,
  secret: string,
): SessionInfo {
  const cookies = parseCookies(request);
  const existingUserId = parseSignedSession(cookies[SESSION_COOKIE_NAME], secret);
  const userId = existingUserId || randomUUID();
  if (!existingUserId) {
    appendSetCookie(
      responseHeaders,
      SESSION_COOKIE_NAME,
      serializeSessionValue(userId, secret),
      {
        httpOnly: true,
        maxAge: SESSION_MAX_AGE_SECONDS,
        path: "/",
        sameSite: "lax",
        secure: isSecureRequest(request),
      },
    );
  }
  return { user: buildUser(userId) };
}

export function clearSession(request: Request, responseHeaders: Headers): void {
  appendExpiredCookie(responseHeaders, SESSION_COOKIE_NAME, isSecureRequest(request));
}
