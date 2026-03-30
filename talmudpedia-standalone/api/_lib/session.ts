import { createHmac, randomUUID } from "node:crypto";

import { listDemoClients } from "./demo-clients.js";
import {
  appendExpiredCookie,
  appendSetCookie,
  isSecureRequest,
  parseCookies,
} from "./http.js";

const SESSION_COOKIE_NAME = "tp_standalone_session";
const SELECTED_CLIENT_COOKIE_NAME = "tp_standalone_selected_client";
const SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 30;

export type SessionInfo = {
  userId: string;
  displayName: string;
  selectedClientId: string | null;
  availableClients: Array<{
    id: string;
    name: string;
    sector: string;
    baseCurrency: string;
  }>;
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

function formatDisplayName(userId: string): string {
  return `Local User ${userId.slice(-8).toUpperCase()}`;
}

function normalizeSelectedClient(raw: string | undefined): string | null {
  const value = String(raw || "").trim();
  if (!value) {
    return null;
  }

  return listDemoClients().some((client) => client.id === value) ? value : null;
}

export function ensureSession(
  request: Request,
  responseHeaders: Headers,
  secret: string,
): SessionInfo {
  const cookies = parseCookies(request);
  const existingUserId = parseSignedSession(cookies[SESSION_COOKIE_NAME], secret);
  const userId = existingUserId || randomUUID();
  const secure = isSecureRequest(request);

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
        secure,
      },
    );
  }

  return {
    userId,
    displayName: formatDisplayName(userId),
    selectedClientId:
      normalizeSelectedClient(cookies[SELECTED_CLIENT_COOKIE_NAME]) ||
      listDemoClients()[0]?.id ||
      null,
    availableClients: listDemoClients(),
  };
}

export function setSelectedClient(
  request: Request,
  responseHeaders: Headers,
  clientId: string,
): void {
  appendSetCookie(responseHeaders, SELECTED_CLIENT_COOKIE_NAME, clientId, {
    httpOnly: true,
    maxAge: SESSION_MAX_AGE_SECONDS,
    path: "/",
    sameSite: "lax",
    secure: isSecureRequest(request),
  });
}

export function clearSession(request: Request, responseHeaders: Headers): void {
  const secure = isSecureRequest(request);
  appendExpiredCookie(responseHeaders, SESSION_COOKIE_NAME, secure);
  appendExpiredCookie(responseHeaders, SELECTED_CLIENT_COOKIE_NAME, secure);
}
