"use client";

import Link from "next/link";
import { useEffect } from "react";
import { useLayoutStore } from "@/lib/store/useLayoutStore";

type LandingPageProps = {
  title?: string;
  description?: string;
};

export function LandingPage({
  title = "Platform landing rebuild in progress",
  description = "The previous product-specific landing content has been removed. This surface will be rebuilt around the current Talmudpedia platform.",
}: LandingPageProps) {
  const setActiveChatId = useLayoutStore((state) => state.setActiveChatId);

  useEffect(() => {
    setActiveChatId(null);
  }, [setActiveChatId]);

  return (
    <section className="px-6 pb-16 pt-32">
      <div className="mx-auto flex min-h-[calc(100vh-14rem)] w-full max-w-6xl items-center">
        <div className="grid w-full gap-10 lg:grid-cols-[1.35fr_0.9fr]">
          <div className="space-y-8">
            <div className="inline-flex rounded-full border border-slate-300/70 bg-white/70 px-4 py-2 text-xs font-semibold uppercase tracking-[0.32em] text-slate-600 shadow-sm backdrop-blur">
              Cleanup phase
            </div>
            <div className="space-y-5">
              <h1 className="max-w-4xl text-5xl font-semibold tracking-[-0.05em] text-slate-950 md:text-7xl">
                {title}
              </h1>
              {description ? (
                <p className="max-w-3xl text-lg leading-8 text-slate-600 md:text-xl">
                  {description}
                </p>
              ) : null}
            </div>
            <div className="grid gap-4 text-sm text-slate-600 md:grid-cols-3">
              <div className="rounded-3xl border border-slate-200/80 bg-white/75 p-5 shadow-sm backdrop-blur">
                <div className="text-xs font-semibold uppercase tracking-[0.28em] text-slate-500">
                  Status
                </div>
                <p className="mt-3 text-base text-slate-800">
                  Legacy marketing and old domain language have been removed.
                </p>
              </div>
              <div className="rounded-3xl border border-slate-200/80 bg-white/75 p-5 shadow-sm backdrop-blur">
                <div className="text-xs font-semibold uppercase tracking-[0.28em] text-slate-500">
                  Current focus
                </div>
                <p className="mt-3 text-base text-slate-800">
                  Apps, agents, RAG, tools, governance, and runtime surfaces.
                </p>
              </div>
              <div className="rounded-3xl border border-slate-200/80 bg-white/75 p-5 shadow-sm backdrop-blur">
                <div className="text-xs font-semibold uppercase tracking-[0.28em] text-slate-500">
                  Next phase
                </div>
                <p className="mt-3 text-base text-slate-800">
                  Build a new landing system around the actual platform product.
                </p>
              </div>
            </div>
          </div>

          <aside className="rounded-[2rem] border border-slate-200/80 bg-white/80 p-8 shadow-[0_30px_80px_rgba(15,23,42,0.08)] backdrop-blur-xl">
            <div className="space-y-8">
              <div>
                <div className="text-xs font-semibold uppercase tracking-[0.28em] text-slate-500">
                  Temporary entry points
                </div>
                <p className="mt-3 text-sm leading-7 text-slate-600">
                  Until the new landing direction is designed, route users straight into the working platform surfaces.
                </p>
              </div>
              <div className="space-y-3">
                <Link
                  href="/auth/login"
                  className="flex items-center justify-between rounded-2xl border border-slate-200 bg-slate-950 px-5 py-4 text-sm font-medium text-white transition-transform hover:-translate-y-0.5"
                >
                  <span>Sign in</span>
                  <span className="text-white/60">/auth/login</span>
                </Link>
                <Link
                  href="/admin/apps"
                  className="flex items-center justify-between rounded-2xl border border-slate-200 bg-white px-5 py-4 text-sm font-medium text-slate-900 transition-transform hover:-translate-y-0.5"
                >
                  <span>Open apps</span>
                  <span className="text-slate-400">/admin/apps</span>
                </Link>
                <Link
                  href="/admin/agents"
                  className="flex items-center justify-between rounded-2xl border border-slate-200 bg-white px-5 py-4 text-sm font-medium text-slate-900 transition-transform hover:-translate-y-0.5"
                >
                  <span>Open agents</span>
                  <span className="text-slate-400">/admin/agents</span>
                </Link>
              </div>
            </div>
          </aside>
        </div>
      </div>
    </section>
  );
}
