"use client";

import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo } from "react";
import { Loader2 } from "lucide-react";

import { setPublishedAppToken } from "@/lib/store/usePublishedAppAuthStore";

export default function PublishedAppAuthCallbackPage() {
  const params = useParams<{ appSlug: string }>();
  const router = useRouter();
  const search = useSearchParams();
  const appSlug = params?.appSlug || "";

  const token = useMemo(() => search.get("token"), [search]);
  const appSlugFromQuery = useMemo(() => search.get("appSlug"), [search]);

  useEffect(() => {
    const effectiveSlug = appSlugFromQuery || appSlug;
    if (token && effectiveSlug) {
      setPublishedAppToken(effectiveSlug, token);
      router.replace(`/published/${effectiveSlug}`);
      return;
    }
    router.replace(`/published/${appSlug}/login`);
  }, [appSlug, appSlugFromQuery, router, token]);

  return (
    <div className="flex h-screen items-center justify-center text-muted-foreground">
      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
      Completing sign in...
    </div>
  );
}
