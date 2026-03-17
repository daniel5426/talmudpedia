import type { Request, Response } from "express";
import { createHmac, randomUUID } from "node:crypto";

const SESSION_COOKIE_NAME = "tp_standalone_session";

export type SessionInfo = {
  userId: string;
  displayName: string;
};

function signValue(value: string, secret: string): string {
  return createHmac("sha256", secret).update(value).digest("hex");
}

function serializeSessionValue(userId: string, secret: string): string {
  return `${userId}.${signValue(userId, secret)}`;
}

function parseSignedSession(raw: string | undefined, secret: string): string | null {
  const value = String(raw || "").trim();
  if (!value) return null;
  const pivot = value.lastIndexOf(".");
  if (pivot <= 0) return null;
  const userId = value.slice(0, pivot);
  const signature = value.slice(pivot + 1);
  return signValue(userId, secret) === signature ? userId : null;
}

function formatDisplayName(userId: string): string {
  const suffix = userId.slice(-8).toUpperCase();
  return `Local User ${suffix}`;
}

export function ensureSession(req: Request, res: Response, secret: string): SessionInfo {
  const existingUserId = parseSignedSession(req.cookies?.[SESSION_COOKIE_NAME], secret);
  const userId = existingUserId || randomUUID();
  if (!existingUserId) {
    res.cookie(SESSION_COOKIE_NAME, serializeSessionValue(userId, secret), {
      httpOnly: true,
      sameSite: "lax",
      secure: false,
      path: "/",
      maxAge: 1000 * 60 * 60 * 24 * 30,
    });
  }
  return {
    userId,
    displayName: formatDisplayName(userId),
  };
}

export function clearSession(res: Response): void {
  res.clearCookie(SESSION_COOKIE_NAME, {
    httpOnly: true,
    sameSite: "lax",
    secure: false,
    path: "/",
  });
}
