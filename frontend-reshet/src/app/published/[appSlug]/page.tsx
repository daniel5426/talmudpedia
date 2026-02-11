"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { Loader2, LogOut, Send, ShieldCheck } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { clearPublishedAppToken, getPublishedAppToken } from "@/lib/store/usePublishedAppAuthStore";
import { publishedRuntimeService } from "@/services";
import type { PublicChatItem, PublishedRuntimeConfig, PublishedRuntimeUser } from "@/services";
import { compileReactArtifactProject } from "@/lib/react-artifacts/compiler";

type ChatMessage = { role: string; content: string };

function normalizeSseEvent(raw: string): Record<string, any> | null {
  const lines = raw.split("\n");
  for (const line of lines) {
    if (!line.startsWith("data: ")) continue;
    const payload = line.slice(6).trim();
    if (!payload) continue;
    try {
      return JSON.parse(payload);
    } catch {
      return null;
    }
  }
  return null;
}

type RuntimeContext = {
  mode: "builder-preview" | "published-runtime";
  appSlug?: string;
  token?: string | null;
  basePath?: string;
};

function buildPreviewHtml(bundle: string, css?: string, runtimeContext?: RuntimeContext): string {
  const safeBundle = bundle.replace(/<\/(script)/gi, "<\\/$1");
  const safeCss = (css || "").replace(/<\/(style)/gi, "<\\/$1");
  const contextJson = runtimeContext
    ? JSON.stringify(runtimeContext).replace(/<\/(script)/gi, "<\\/$1")
    : "";
  return `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline' https://cdn.tailwindcss.com;" />
    <style>
      * { box-sizing: border-box; }
      html, body { margin: 0; padding: 0; width: 100%; height: 100%; }
      body { font-family: ui-sans-serif, system-ui, -apple-system, sans-serif; background: #fff; color: #111827; }
      #root { width: 100%; height: 100%; }
    </style>
    ${safeCss ? `<style>${safeCss}</style>` : ""}
  </head>
  <body>
    <div id="root"></div>
    <script src="https://cdn.tailwindcss.com"></script>
    ${contextJson ? `<script>window.__APP_RUNTIME_CONTEXT = ${contextJson};</script>` : ""}
    <script>${safeBundle}</script>
  </body>
</html>`;
}

export default function PublishedAppPage() {
  const params = useParams<{ appSlug: string }>();
  const router = useRouter();
  const appSlug = params?.appSlug || "";
  const token = useMemo(() => getPublishedAppToken(appSlug), [appSlug]);

  const [config, setConfig] = useState<PublishedRuntimeConfig | null>(null);
  const [viewer, setViewer] = useState<PublishedRuntimeUser | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [chatId, setChatId] = useState<string | null>(null);
  const [history, setHistory] = useState<PublicChatItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [customUISrcDoc, setCustomUISrcDoc] = useState<string | null>(null);
  const [customUIError, setCustomUIError] = useState<string | null>(null);

  async function loadConfig() {
    if (!appSlug) return;
    setIsLoading(true);
    setError(null);
    try {
      const nextConfig = await publishedRuntimeService.getConfig(appSlug);
      setConfig(nextConfig);

      if (nextConfig.status !== "published") {
        setIsLoading(false);
        return;
      }

      if (nextConfig.auth_enabled) {
        if (!token) {
          router.replace(`/published/${appSlug}/login`);
          return;
        }
        const me = await publishedRuntimeService.getMe(appSlug, token);
        setViewer(me);
        const list = await publishedRuntimeService.listChats(appSlug, token);
        setHistory(list.items);
      }

      if (nextConfig.has_custom_ui && nextConfig.ui_runtime_mode === "custom_bundle") {
        try {
          const ui = await publishedRuntimeService.getUI(appSlug);
          const compileResult = await compileReactArtifactProject(ui.files || {}, ui.entry_file || "src/main.tsx");
          if (!compileResult.ok) {
            setCustomUIError(compileResult.error);
          } else {
            setCustomUISrcDoc(
              buildPreviewHtml(compileResult.output, compileResult.css, {
                mode: "published-runtime",
                appSlug,
                token,
              }),
            );
          }
        } catch (uiErr) {
          setCustomUIError(uiErr instanceof Error ? uiErr.message : "Failed to load custom UI");
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load app");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    loadConfig();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [appSlug]);

  async function loadChatHistory(nextChatId: string) {
    if (!token) return;
    try {
      const chat = await publishedRuntimeService.getChat(appSlug, nextChatId, token);
      setChatId(chat.id);
      setMessages(chat.messages.map((message) => ({ role: message.role, content: message.content })));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load chat history");
    }
  }

  async function handleLogout() {
    if (!token) return;
    try {
      await publishedRuntimeService.logout(appSlug, token);
    } catch {
      // best-effort logout
    } finally {
      clearPublishedAppToken(appSlug);
      router.replace(`/published/${appSlug}/login`);
    }
  }

  async function sendMessage(event: FormEvent) {
    event.preventDefault();
    const nextInput = input.trim();
    if (!nextInput || isSending || !config) return;

    setIsSending(true);
    setError(null);
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: nextInput }, { role: "assistant", content: "" }]);

    try {
      const response = await publishedRuntimeService.streamChat(
        appSlug,
        { input: nextInput, chat_id: chatId || undefined },
        config.auth_enabled ? token || undefined : undefined,
      );
      const incomingChatId = response.headers.get("X-Chat-ID");
      if (incomingChatId) {
        setChatId(incomingChatId);
      }

      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error("Streaming is not supported in this browser.");
      }

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        let splitIndex = buffer.indexOf("\n\n");
        while (splitIndex >= 0) {
          const raw = buffer.slice(0, splitIndex).trim();
          buffer = buffer.slice(splitIndex + 2);

          const parsed = normalizeSseEvent(raw);
          if (parsed) {
            if (parsed.type === "error") {
              setError(parsed.error || parsed.data?.message || "Streaming error");
            }
            const tokenChunk =
              (parsed.event === "token" && parsed.data?.content)
                ? String(parsed.data.content)
                : (parsed.type === "token" && parsed.content)
                  ? String(parsed.content)
                  : "";
            if (tokenChunk) {
              setMessages((prev) => {
                const next = [...prev];
                const lastIndex = next.length - 1;
                if (lastIndex >= 0 && next[lastIndex].role === "assistant") {
                  next[lastIndex] = {
                    ...next[lastIndex],
                    content: `${next[lastIndex].content}${tokenChunk}`,
                  };
                }
                return next;
              });
            }
          }

          splitIndex = buffer.indexOf("\n\n");
        }
      }

      if (config.auth_enabled && token) {
        const list = await publishedRuntimeService.listChats(appSlug, token);
        setHistory(list.items);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send message");
    } finally {
      setIsSending(false);
    }
  }

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center text-muted-foreground">
        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
        Loading app...
      </div>
    );
  }

  if (error && !config) {
    return (
      <div className="mx-auto max-w-xl p-6">
        <Card>
          <CardHeader>
            <CardTitle>App Not Available</CardTitle>
            <CardDescription>{error}</CardDescription>
          </CardHeader>
        </Card>
      </div>
    );
  }

  if (!config) {
    return null;
  }

  if (config.status !== "published") {
    return (
      <div className="mx-auto max-w-xl p-6">
        <Card>
          <CardHeader>
            <CardTitle>App Unavailable</CardTitle>
            <CardDescription>Status: {config.status}</CardDescription>
          </CardHeader>
        </Card>
      </div>
    );
  }

  if (config.has_custom_ui && config.ui_runtime_mode === "custom_bundle") {
    return (
      <div className="h-screen w-full bg-background">
        {customUIError ? (
          <div className="mx-auto max-w-xl p-6">
            <Card>
              <CardHeader>
                <CardTitle>Custom UI Unavailable</CardTitle>
                <CardDescription>{customUIError}</CardDescription>
              </CardHeader>
            </Card>
          </div>
        ) : customUISrcDoc ? (
          <iframe className="h-full w-full" title="Published App UI" sandbox="allow-scripts" srcDoc={customUISrcDoc} />
        ) : (
          <div className="flex h-screen items-center justify-center text-muted-foreground">
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            Loading app UI...
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="mx-auto flex h-screen w-full max-w-6xl gap-4 p-4">
      {config.auth_enabled ? (
        <Card className="hidden w-72 shrink-0 md:flex md:flex-col">
          <CardHeader>
            <CardTitle className="text-base">{config.name}</CardTitle>
            <CardDescription>Chat history</CardDescription>
          </CardHeader>
          <CardContent className="flex-1 overflow-hidden">
            <ScrollArea className="h-full">
              <div className="space-y-2">
                {history.map((item) => (
                  <Button
                    key={item.id}
                    variant={item.id === chatId ? "default" : "outline"}
                    className="w-full justify-start"
                    onClick={() => loadChatHistory(item.id)}
                  >
                    {item.title || "Untitled chat"}
                  </Button>
                ))}
              </div>
            </ScrollArea>
          </CardContent>
        </Card>
      ) : null}

      <Card className="flex min-w-0 flex-1 flex-col">
        <CardHeader className="border-b">
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>{config.name}</CardTitle>
              <CardDescription className="flex items-center gap-2">
                <ShieldCheck className="h-4 w-4" />
                {config.auth_enabled ? "Auth-enabled app" : "Public app"}
              </CardDescription>
            </div>
            {config.auth_enabled && viewer ? (
              <div className="flex items-center gap-2">
                <span className="text-sm text-muted-foreground">{viewer.email}</span>
                <Button variant="outline" size="sm" onClick={handleLogout}>
                  <LogOut className="mr-2 h-4 w-4" />
                  Logout
                </Button>
              </div>
            ) : (
              <Button asChild variant="outline" size="sm">
                <Link href={`/published/${appSlug}/login`}>Login</Link>
              </Button>
            )}
          </div>
        </CardHeader>

        <CardContent className="flex min-h-0 flex-1 flex-col gap-4 p-4">
          <ScrollArea className="h-full rounded-md border p-3">
            <div className="space-y-3">
              {messages.length === 0 ? (
                <div className="text-sm text-muted-foreground">Start a conversation with this published app.</div>
              ) : (
                messages.map((message, index) => (
                  <div
                    key={`${index}-${message.role}`}
                    className={`rounded-md p-3 text-sm ${
                      message.role === "user" ? "ml-auto max-w-[85%] bg-primary text-primary-foreground" : "max-w-[90%] bg-muted"
                    }`}
                  >
                    {message.content || (message.role === "assistant" && isSending ? "..." : "")}
                  </div>
                ))
              )}
            </div>
          </ScrollArea>

          <form className="flex items-center gap-2" onSubmit={sendMessage}>
            <Input
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder="Send a message..."
              disabled={isSending}
            />
            <Button type="submit" disabled={isSending || !input.trim()}>
              {isSending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            </Button>
          </form>
          {error ? <div className="text-sm text-destructive">{error}</div> : null}
        </CardContent>
      </Card>
    </div>
  );
}
