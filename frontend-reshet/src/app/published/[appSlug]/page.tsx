"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Loader2 } from "lucide-react";

import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { publishedRuntimeService } from "@/services";

function normalizePathname(pathname: string): string {
  if (!pathname) return "/";
  const trimmed = pathname.endsWith("/") && pathname !== "/" ? pathname.slice(0, -1) : pathname;
  return trimmed || "/";
}

function isSameUrlTarget(target: string): boolean {
  try {
    const current = new URL(window.location.href);
    const resolvedTarget = new URL(target, current.href);
    return (
      current.origin === resolvedTarget.origin &&
      normalizePathname(current.pathname) === normalizePathname(resolvedTarget.pathname) &&
      current.search === resolvedTarget.search &&
      current.hash === resolvedTarget.hash
    );
  } catch {
    return false;
  }
}

export default function PublishedAppPage() {
  const params = useParams<{ appSlug: string }>();
  const appSlug = params?.appSlug || "";
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function resolveRuntime() {
      if (!appSlug) return;
      setError(null);
      try {
        const runtime = await publishedRuntimeService.getRuntime(appSlug);
        if (!runtime.published_url) {
          throw new Error("Published runtime URL is unavailable");
        }
        if (isSameUrlTarget(runtime.published_url)) {
          throw new Error(
            "Published runtime URL resolves to the current page, causing a redirect loop. " +
              "Use a different published URL host/path for runtime assets in local mode.",
          );
        }
        if (!cancelled) {
          window.location.replace(runtime.published_url);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to resolve published runtime");
        }
      }
    }

    resolveRuntime();
    return () => {
      cancelled = true;
    };
  }, [appSlug]);

  if (error) {
    return (
      <div className="mx-auto flex h-screen w-full max-w-xl items-center p-6">
        <Card className="w-full">
          <CardHeader>
            <CardTitle>Published Runtime Unavailable</CardTitle>
            <CardDescription>{error}</CardDescription>
          </CardHeader>
        </Card>
      </div>
    );
  }

  return (
    <div className="flex h-screen items-center justify-center text-muted-foreground">
      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
      Redirecting to published app...
    </div>
  );
}
