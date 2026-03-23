"use client";

import { useEffect, useState, useRef } from "react";
import Link from "next/link";
import {
  ArrowRight,
  ArrowUpRight,
  Workflow,
  Database,
  Blocks,
  Shield,
  Cpu,
  Layers,
  GitBranch,
  Network,
  Box,
  Gauge,
} from "lucide-react";

/* ───────────────────────────────────────────
   V5 — BENTO GRID
   Apple-style product showcase, mixed-media
   card grids, interactive hover states,
   clean white + deep charcoal, tight details
   ─────────────────────────────────────────── */

function BentoCard({
  children,
  className = "",
  hover = true,
}: {
  children: React.ReactNode;
  className?: string;
  hover?: boolean;
}) {
  return (
    <div
      className={`group relative overflow-hidden rounded-3xl border border-slate-200/80 bg-white p-6 transition-all duration-500 ${
        hover ? "hover:-translate-y-0.5 hover:border-slate-300 hover:shadow-xl hover:shadow-slate-200/50" : ""
      } ${className}`}
    >
      {children}
    </div>
  );
}

function AnimatedCounter({ target, suffix = "" }: { target: string; suffix?: string }) {
  const [visible, setVisible] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    const observer = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting) setVisible(true); },
      { threshold: 0.5 }
    );
    if (ref.current) observer.observe(ref.current);
    return () => observer.disconnect();
  }, []);

  return (
    <span
      ref={ref}
      className={`transition-all duration-1000 ${
        visible ? "translate-y-0 opacity-100" : "translate-y-4 opacity-0"
      }`}
    >
      {target}{suffix}
    </span>
  );
}

export function LandingV5() {
  const [mounted, setMounted] = useState(false);
  const [activeLayer, setActiveLayer] = useState(4);
  useEffect(() => setMounted(true), []);

  const layers = [
    { n: 0, name: "Foundation", desc: "Tenancy, identity, policy", color: "bg-slate-100" },
    { n: 1, name: "Resources", desc: "Models, tools, artifacts", color: "bg-slate-200" },
    { n: 2, name: "RAG", desc: "Pipelines, knowledge, retrieval", color: "bg-slate-300" },
    { n: 3, name: "Agents", desc: "Graphs, execution, traces", color: "bg-slate-500 text-white" },
    { n: 4, name: "Applications", desc: "Published apps, widgets", color: "bg-slate-900 text-white" },
  ];

  return (
    <div className="relative min-h-screen bg-[#fafafa] text-slate-900 selection:bg-slate-900 selection:text-white">
      {/* Subtle noise texture */}
      <div
        className="pointer-events-none fixed inset-0 opacity-[0.015]"
        style={{
          backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E")`,
        }}
      />

      {/* Nav */}
      <nav
        className={`fixed top-0 z-50 w-full transition-all duration-700 ${
          mounted ? "translate-y-0 opacity-100" : "-translate-y-4 opacity-0"
        }`}
      >
        <div className="mx-auto max-w-7xl px-6 py-4">
          <div className="flex items-center justify-between rounded-2xl border border-slate-200 bg-white/80 px-5 py-3 shadow-sm backdrop-blur-xl">
            <div className="flex items-center gap-3">
              <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-slate-900 text-xs font-bold text-white">
                TP
              </div>
              <span className="text-sm font-semibold tracking-[-0.02em]">
                Talmudpedia
              </span>
            </div>
            <div className="hidden items-center gap-8 md:flex">
              <span className="cursor-pointer text-sm text-slate-500 transition-colors hover:text-slate-900">
                Platform
              </span>
              <span className="cursor-pointer text-sm text-slate-500 transition-colors hover:text-slate-900">
                Products
              </span>
              <span className="cursor-pointer text-sm text-slate-500 transition-colors hover:text-slate-900">
                Pricing
              </span>
              <span className="cursor-pointer text-sm text-slate-500 transition-colors hover:text-slate-900">
                Docs
              </span>
            </div>
            <Link
              href="/auth/login"
              className="group flex items-center gap-1.5 rounded-xl bg-slate-900 px-5 py-2 text-sm font-medium text-white transition-all duration-300 hover:bg-slate-800"
            >
              Sign in
              <ArrowRight className="h-3.5 w-3.5 transition-transform duration-300 group-hover:translate-x-0.5" />
            </Link>
          </div>
        </div>
      </nav>

      {/* Hero */}
      <section className="relative px-6 pb-16 pt-32 md:pt-40">
        <div
          className={`mx-auto max-w-4xl text-center transition-all duration-1000 delay-200 ${
            mounted ? "translate-y-0 opacity-100" : "translate-y-12 opacity-0"
          }`}
        >
          <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-4 py-1.5 shadow-sm">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
            <span className="text-xs font-medium text-slate-600">
              Platform beta — now open
            </span>
          </div>

          <h1 className="text-5xl font-semibold leading-[1.05] tracking-[-0.045em] text-slate-900 md:text-7xl">
            The AI platform
            <br />
            you actually want
          </h1>

          <p className="mx-auto mt-6 max-w-xl text-base leading-relaxed text-slate-500 md:text-lg">
            Agents, RAG, apps, governance — designed as one unified system.
            Not glued together, built together.
          </p>

          <div className="mt-8 flex flex-col items-center gap-3 sm:flex-row sm:justify-center">
            <Link
              href="/auth/login"
              className="group flex items-center gap-2 rounded-2xl bg-slate-900 px-8 py-4 text-sm font-semibold text-white transition-all duration-300 hover:bg-slate-800 hover:shadow-xl hover:shadow-slate-300/30"
            >
              Start building
              <ArrowRight className="h-4 w-4 transition-transform duration-300 group-hover:translate-x-1" />
            </Link>
            <Link
              href="/admin/apps"
              className="flex items-center gap-2 rounded-2xl border border-slate-200 bg-white px-8 py-4 text-sm font-medium text-slate-700 transition-all duration-300 hover:border-slate-300 hover:shadow-md"
            >
              Explore demo
              <ArrowUpRight className="h-4 w-4" />
            </Link>
          </div>
        </div>
      </section>

      {/* Bento Grid — Main */}
      <section className="px-6 pb-20">
        <div className="mx-auto max-w-7xl">
          <div className="grid gap-4 md:grid-cols-3">
            {/* Large feature card — Agent Graphs */}
            <BentoCard className="md:col-span-2 md:row-span-2">
              <div className="flex h-full flex-col">
                <div className="mb-4 flex items-center gap-2">
                  <Workflow className="h-4 w-4 text-slate-400" strokeWidth={1.5} />
                  <span className="text-xs font-medium uppercase tracking-[0.15em] text-slate-400">
                    Agent Graphs
                  </span>
                </div>
                <h3 className="mb-3 text-2xl font-semibold tracking-[-0.03em] text-slate-900 md:text-3xl">
                  Design reasoning
                  <br />
                  as visual flows
                </h3>
                <p className="mb-6 max-w-md text-sm leading-relaxed text-slate-500">
                  Compose logic, tools, retrieval, and orchestration nodes into
                  executable agent architectures. Every node is typed, every
                  edge is validated.
                </p>
                {/* Mini graph visualization */}
                <div className="mt-auto rounded-2xl border border-slate-100 bg-slate-50 p-6">
                  <div className="flex items-center justify-between">
                    {[
                      { icon: Box, label: "Input" },
                      { icon: Cpu, label: "Reason" },
                      { icon: Database, label: "Retrieve" },
                      { icon: GitBranch, label: "Branch" },
                      { icon: Network, label: "Output" },
                    ].map((node, i) => (
                      <div key={node.label} className="flex flex-col items-center gap-2">
                        <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-slate-200 bg-white shadow-sm transition-all duration-300 group-hover:shadow-md">
                          <node.icon className="h-4 w-4 text-slate-600" strokeWidth={1.5} />
                        </div>
                        <span className="text-[10px] text-slate-400">{node.label}</span>
                        {i < 4 && (
                          <div className="absolute hidden" />
                        )}
                      </div>
                    ))}
                  </div>
                  {/* Connection lines */}
                  <div className="mx-auto mt-[-28px] mb-6 flex items-center justify-between px-8">
                    {Array.from({ length: 4 }).map((_, i) => (
                      <div key={i} className="h-[1px] flex-1 bg-slate-200" />
                    ))}
                  </div>
                </div>
              </div>
            </BentoCard>

            {/* RAG */}
            <BentoCard>
              <Database className="mb-4 h-5 w-5 text-slate-400" strokeWidth={1.5} />
              <h3 className="mb-2 text-base font-semibold tracking-[-0.02em] text-slate-900">
                RAG Pipelines
              </h3>
              <p className="text-sm leading-relaxed text-slate-500">
                Ingest, chunk, embed, and retrieve. Graph-based operators with
                knowledge store abstraction.
              </p>
              <div className="mt-4 flex gap-1.5">
                {["Chunking", "Embedding", "Retrieval"].map((t) => (
                  <span
                    key={t}
                    className="rounded-full bg-slate-100 px-2.5 py-1 text-[10px] font-medium text-slate-500"
                  >
                    {t}
                  </span>
                ))}
              </div>
            </BentoCard>

            {/* Artifacts */}
            <BentoCard>
              <Blocks className="mb-4 h-5 w-5 text-slate-400" strokeWidth={1.5} />
              <h3 className="mb-2 text-base font-semibold tracking-[-0.02em] text-slate-900">
                Artifact Extensions
              </h3>
              <p className="text-sm leading-relaxed text-slate-500">
                Deploy custom code as platform extensions. Execute at the edge
                via Cloudflare Workers.
              </p>
              <div className="mt-4 flex gap-1.5">
                {["Edge", "Tools", "Operators"].map((t) => (
                  <span
                    key={t}
                    className="rounded-full bg-slate-100 px-2.5 py-1 text-[10px] font-medium text-slate-500"
                  >
                    {t}
                  </span>
                ))}
              </div>
            </BentoCard>

            {/* Stats row */}
            <BentoCard className="flex flex-col items-center justify-center text-center" hover={false}>
              <Gauge className="mb-2 h-5 w-5 text-emerald-500" />
              <div className="text-3xl font-bold tracking-[-0.03em] text-slate-900">
                <AnimatedCounter target="<200" suffix="ms" />
              </div>
              <div className="text-xs text-slate-400">Agent cold-start p95</div>
            </BentoCard>

            <BentoCard className="flex flex-col items-center justify-center text-center" hover={false}>
              <Shield className="mb-2 h-5 w-5 text-blue-500" />
              <div className="text-3xl font-bold tracking-[-0.03em] text-slate-900">
                <AnimatedCounter target="100" suffix="%" />
              </div>
              <div className="text-xs text-slate-400">Tenant isolation</div>
            </BentoCard>

            <BentoCard className="flex flex-col items-center justify-center text-center" hover={false}>
              <Layers className="mb-2 h-5 w-5 text-violet-500" />
              <div className="text-3xl font-bold tracking-[-0.03em] text-slate-900">
                <AnimatedCounter target="5" suffix=" layers" />
              </div>
              <div className="text-xs text-slate-400">Clean architecture</div>
            </BentoCard>
          </div>
        </div>
      </section>

      {/* Bento Grid — Architecture + Models */}
      <section className="px-6 pb-20">
        <div className="mx-auto max-w-7xl">
          <div className="grid gap-4 md:grid-cols-3">
            {/* Architecture interactive */}
            <BentoCard className="md:col-span-2">
              <div className="mb-4 flex items-center gap-2">
                <Layers className="h-4 w-4 text-slate-400" />
                <span className="text-xs font-medium uppercase tracking-[0.15em] text-slate-400">
                  Architecture
                </span>
              </div>
              <h3 className="mb-6 text-xl font-semibold tracking-[-0.02em] text-slate-900">
                Five layers, clear contracts
              </h3>
              <div className="flex flex-col gap-2">
                {layers.map((l) => (
                  <button
                    key={l.n}
                    type="button"
                    onClick={() => setActiveLayer(l.n)}
                    className={`flex items-center justify-between rounded-xl px-5 py-3 text-left transition-all duration-300 ${
                      activeLayer === l.n
                        ? `${l.color} shadow-md`
                        : "bg-slate-50 text-slate-600 hover:bg-slate-100"
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      <span className="font-mono text-xs opacity-50">L{l.n}</span>
                      <span className="text-sm font-medium">{l.name}</span>
                    </div>
                    <span className={`text-xs ${activeLayer === l.n ? "opacity-70" : "text-slate-400"}`}>
                      {l.desc}
                    </span>
                  </button>
                ))}
              </div>
            </BentoCard>

            {/* Model registry */}
            <BentoCard>
              <Cpu className="mb-4 h-5 w-5 text-slate-400" strokeWidth={1.5} />
              <h3 className="mb-2 text-base font-semibold tracking-[-0.02em] text-slate-900">
                Model Registry
              </h3>
              <p className="mb-4 text-sm leading-relaxed text-slate-500">
                Manage models across every provider in one place.
              </p>
              <div className="space-y-2">
                {[
                  { name: "GPT-4o", provider: "OpenAI", status: "active" },
                  { name: "Claude Opus", provider: "Anthropic", status: "active" },
                  { name: "Gemini 2", provider: "Google", status: "configured" },
                ].map((m) => (
                  <div
                    key={m.name}
                    className="flex items-center justify-between rounded-lg border border-slate-100 bg-slate-50 px-3 py-2"
                  >
                    <div>
                      <div className="text-xs font-medium text-slate-700">{m.name}</div>
                      <div className="text-[10px] text-slate-400">{m.provider}</div>
                    </div>
                    <span
                      className={`h-1.5 w-1.5 rounded-full ${
                        m.status === "active" ? "bg-emerald-500" : "bg-slate-300"
                      }`}
                    />
                  </div>
                ))}
              </div>
            </BentoCard>
          </div>
        </div>
      </section>

      {/* Published Apps showcase */}
      <section className="px-6 pb-20">
        <div className="mx-auto max-w-7xl">
          <BentoCard className="!p-0 overflow-hidden" hover={false}>
            <div className="grid md:grid-cols-2">
              <div className="p-8 md:p-12">
                <div className="mb-4 flex items-center gap-2">
                  <GitBranch className="h-4 w-4 text-slate-400" />
                  <span className="text-xs font-medium uppercase tracking-[0.15em] text-slate-400">
                    Published Apps
                  </span>
                </div>
                <h3 className="mb-4 text-2xl font-semibold tracking-[-0.03em] text-slate-900 md:text-3xl">
                  Ship AI applications
                  <br />
                  to real users
                </h3>
                <p className="mb-6 text-sm leading-relaxed text-slate-500">
                  Deploy complete AI-powered apps with custom PRICO widget
                  layouts, embedded agent runtimes, and interactive surfaces.
                  From prototype to production in minutes.
                </p>
                <Link
                  href="/admin/apps"
                  className="group inline-flex items-center gap-2 rounded-xl bg-slate-900 px-6 py-3 text-sm font-medium text-white transition-all duration-300 hover:bg-slate-800"
                >
                  View apps
                  <ArrowRight className="h-4 w-4 transition-transform duration-300 group-hover:translate-x-1" />
                </Link>
              </div>
              {/* Mock app preview */}
              <div className="border-t border-slate-100 bg-slate-50 p-8 md:border-l md:border-t-0">
                <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                  <div className="mb-4 flex items-center gap-2">
                    <div className="h-3 w-3 rounded-full bg-slate-200" />
                    <div className="h-3 w-3 rounded-full bg-slate-200" />
                    <div className="h-3 w-3 rounded-full bg-slate-200" />
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div className="rounded-xl bg-slate-50 p-3">
                      <div className="mb-2 h-2 w-16 rounded bg-slate-200" />
                      <div className="h-16 rounded-lg bg-gradient-to-br from-slate-100 to-slate-50" />
                    </div>
                    <div className="rounded-xl bg-slate-50 p-3">
                      <div className="mb-2 h-2 w-12 rounded bg-slate-200" />
                      <div className="space-y-1.5">
                        <div className="h-2 w-full rounded bg-slate-100" />
                        <div className="h-2 w-3/4 rounded bg-slate-100" />
                        <div className="h-2 w-1/2 rounded bg-slate-100" />
                      </div>
                    </div>
                    <div className="col-span-2 rounded-xl bg-slate-50 p-3">
                      <div className="mb-2 h-2 w-20 rounded bg-slate-200" />
                      <div className="flex gap-2">
                        <div className="h-8 flex-1 rounded-lg bg-slate-900" />
                        <div className="h-8 flex-1 rounded-lg bg-slate-100" />
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </BentoCard>
        </div>
      </section>

      {/* CTA */}
      <section className="px-6 pb-32">
        <div className="mx-auto max-w-7xl">
          <div className="rounded-3xl bg-slate-900 px-8 py-20 text-center md:px-20">
            <h2 className="mb-4 text-3xl font-semibold tracking-[-0.03em] text-white md:text-5xl">
              Ready to build?
            </h2>
            <p className="mx-auto mb-10 max-w-md text-sm text-slate-400">
              From first agent to production deployment. Everything you need in
              one unified platform.
            </p>
            <div className="flex flex-col items-center gap-3 sm:flex-row sm:justify-center">
              <Link
                href="/auth/login"
                className="group flex items-center gap-2 rounded-2xl bg-white px-8 py-4 text-sm font-semibold text-slate-900 transition-all duration-300 hover:bg-slate-100"
              >
                Create account
                <ArrowRight className="h-4 w-4 transition-transform duration-300 group-hover:translate-x-1" />
              </Link>
              <Link
                href="/admin/apps"
                className="flex items-center gap-2 rounded-2xl border border-slate-700 px-8 py-4 text-sm text-slate-400 transition-all duration-300 hover:border-slate-600 hover:text-white"
              >
                Explore platform
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-slate-200 px-6 py-10">
        <div className="mx-auto flex max-w-7xl flex-col gap-6 md:flex-row md:items-center md:justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-slate-900 text-[10px] font-bold text-white">
              TP
            </div>
            <span className="text-sm font-semibold text-slate-700">Talmudpedia</span>
          </div>
          <div className="flex gap-8">
            <span className="cursor-pointer text-sm text-slate-400 transition-colors hover:text-slate-600">Platform</span>
            <span className="cursor-pointer text-sm text-slate-400 transition-colors hover:text-slate-600">Docs</span>
            <span className="cursor-pointer text-sm text-slate-400 transition-colors hover:text-slate-600">GitHub</span>
            <span className="cursor-pointer text-sm text-slate-400 transition-colors hover:text-slate-600">Status</span>
          </div>
          <span className="text-sm text-slate-400">© 2026 Talmudpedia</span>
        </div>
      </footer>
    </div>
  );
}
