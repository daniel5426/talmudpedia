"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { setPublishedAppToken } from "@/lib/store/usePublishedAppAuthStore";
import { publishedRuntimeService } from "@/services";
import type { PublishedRuntimeConfig } from "@/services";

export default function PublishedAppSignupPage() {
  const params = useParams<{ appSlug: string }>();
  const router = useRouter();
  const appSlug = params?.appSlug || "";

  const [config, setConfig] = useState<PublishedRuntimeConfig | null>(null);
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      setIsLoading(true);
      try {
        const nextConfig = await publishedRuntimeService.getConfig(appSlug);
        setConfig(nextConfig);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load app");
      } finally {
        setIsLoading(false);
      }
    }
    load();
  }, [appSlug]);

  async function handleSignup(event: FormEvent) {
    event.preventDefault();
    setIsSubmitting(true);
    setError(null);
    try {
      const result = await publishedRuntimeService.signup(appSlug, {
        email: email.trim(),
        password,
        full_name: fullName.trim() || undefined,
      });
      setPublishedAppToken(appSlug, result.token);
      router.replace(`/published/${appSlug}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to sign up");
    } finally {
      setIsSubmitting(false);
    }
  }

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center text-muted-foreground">
        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
        Loading signup...
      </div>
    );
  }

  return (
    <div className="mx-auto flex h-screen w-full max-w-md items-center p-4">
      <Card className="w-full">
        <CardHeader>
          <CardTitle>Create Account</CardTitle>
          <CardDescription>Join {config?.name || "this app"} to start chatting.</CardDescription>
        </CardHeader>
        <CardContent>
          <form className="space-y-4" onSubmit={handleSignup}>
            <div className="space-y-2">
              <Label htmlFor="full-name">Full Name</Label>
              <Input id="full-name" value={fullName} onChange={(event) => setFullName(event.target.value)} />
            </div>
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
              Create Account
            </Button>
          </form>
          {error ? <div className="mt-3 text-sm text-destructive">{error}</div> : null}
        </CardContent>
        <CardFooter className="text-sm">
          <span className="text-muted-foreground">
            Already have an account?{" "}
            <Link href={`/published/${appSlug}/login`} className="underline">
              Login
            </Link>
          </span>
        </CardFooter>
      </Card>
    </div>
  );
}
