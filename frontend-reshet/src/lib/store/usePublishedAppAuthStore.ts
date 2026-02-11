"use client";

const KEY_PREFIX = "published-app-auth-token";

function keyFor(appSlug: string): string {
  return `${KEY_PREFIX}:${appSlug}`;
}

export function getPublishedAppToken(appSlug: string): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(keyFor(appSlug));
}

export function setPublishedAppToken(appSlug: string, token: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(keyFor(appSlug), token);
}

export function clearPublishedAppToken(appSlug: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(keyFor(appSlug));
}
