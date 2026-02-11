"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { getPublishedAppToken, setPublishedAppToken } from "@/lib/store/usePublishedAppAuthStore";
import { publishedRuntimeService } from "@/services";
import type { PublishedRuntimeConfig } from "@/services";

export default function PublishedAppLoginPage() {
  const params = useParams<{ appSlug: string }>();
  const router = useRouter();
  const appSlug = params?.appSlug || "";

  const [config, setConfig] = useState<PublishedRuntimeConfig | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const existingToken = useMemo(() => getPublishedAppToken(appSlug), [appSlug]);

  useEffect(() => {
    async function load() {
      setIsLoading(true);
      setError(null);
      try {
        const nextConfig = await publishedRuntimeService.getConfig(appSlug);
        setConfig(nextConfig);
        if (!nextConfig.auth_enabled) {
          router.replace(`/published/${appSlug}`);
          return;
        }
        if (existingToken) {
          try {
            await publishedRuntimeService.getMe(appSlug, existingToken);
            router.replace(`/published/${appSlug}`);
            return;
          } catch {
            // stale token: ignore and keep login screen
          }
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load app login");
      } finally {
        setIsLoading(false);
      }
    }
    load();
  }, [appSlug, existingToken, router]);

  async function handleLogin(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      const auth = await publishedRuntimeService.login(appSlug, { email: email.trim(), password });
      setPublishedAppToken(appSlug, auth.token);
      router.replace(`/published/${appSlug}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to login");
    } finally {
      setIsSubmitting(false);
    }
  }

  function handleGoogleLogin() {
    const returnTo = `${window.location.origin}/published/${appSlug}/auth/callback`;
    window.location.href = publishedRuntimeService.getGoogleStartUrl(appSlug, returnTo);
  }

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center text-muted-foreground">
        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
        Loading login...
      </div>
    );
  }

  if (!config) return null;

  return (
    <div className="mx-auto flex h-screen w-full max-w-md items-center p-4">
      <Card className="w-full">
        <CardHeader>
          <CardTitle>Login to {config.name}</CardTitle>
          <CardDescription>Authenticate to access this published app.</CardDescription>
        </CardHeader>
        <CardContent>
          <form className="space-y-4" onSubmit={handleLogin}>
            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input id="email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                minLength={6}
                required
              />
            </div>
            <Button type="submit" className="w-full" disabled={isSubmitting}>
              {isSubmitting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
              Login
            </Button>
          </form>

          {(config.auth_providers || []).includes("google") ? (
            <Button variant="outline" className="mt-3 w-full" onClick={handleGoogleLogin}>
              Continue with Google
            </Button>
          ) : null}

          {error ? <div className="mt-3 text-sm text-destructive">{error}</div> : null}
        </CardContent>
        <CardFooter className="text-sm">
          <span className="text-muted-foreground">
            No account yet?{" "}
            <Link className="underline" href={`/published/${appSlug}/signup`}>
              Sign up
            </Link>
          </span>
        </CardFooter>
      </Card>
    </div>
  );
}
