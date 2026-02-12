"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Loader2 } from "lucide-react";

import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { publishedRuntimeService } from "@/services";

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
