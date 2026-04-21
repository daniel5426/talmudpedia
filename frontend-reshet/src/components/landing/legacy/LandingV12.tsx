"use client";

import Link from "next/link";
import { ChevronDown, ArrowRight } from "lucide-react";

/* ── bar chart data ─────────────────────────────────────────────── */

const dauBars = [
  2, 4, 3, 5, 6, 4, 7, 5, 8, 6, 4, 3, 7, 9, 8, 6, 5, 7, 10, 8, 11, 9, 7, 8,
  10, 11, 9, 10, 11, 11,
];

const spendBars = [
  0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 2, 1, 3, 5, 4,
  7, 9, 8, 10, 9,
];

const tokenSparkline = [
  1, 1, 0, 0, 0, 0, 0, 0, 1, 0, 0, 1, 1, 2, 3, 2, 4, 5, 6, 8, 10, 9, 12, 14,
  11, 13, 15, 14, 16, 15,
];

/* ── component ──────────────────────────────────────────────────── */

export function LandingV12() {
  return (
    <div className="min-h-screen bg-white text-[#111827] antialiased">
      {/* ── FIXED NAV ─────────────────────────────────────────── */}
      <nav className="fixed top-0 left-0 right-0 z-50 h-16 bg-white/95 backdrop-blur border-b border-gray-100">
        <div className="max-w-[1240px] mx-auto h-full px-6 flex items-center justify-between">
          {/* logo */}
          <Link href="/" className="flex items-center gap-2.5">
            <div className="w-8 h-8 bg-[#111827] rounded-[6px] flex items-center justify-center text-white text-[15px] font-bold leading-none">
              T
            </div>
            <span className="text-[16px] font-bold tracking-[-0.01em]">
              Talmudpedia
            </span>
          </Link>

          {/* center links */}
          <div className="hidden md:flex items-center gap-8">
            <button className="flex items-center gap-1 text-[14px] text-[#4b5563] hover:text-[#111827] transition-colors">
              Platform
              <ChevronDown className="w-3.5 h-3.5" />
            </button>
            <Link
              href="#"
              className="text-[14px] text-[#4b5563] hover:text-[#111827] transition-colors"
            >
              Solutions
            </Link>
            <Link
              href="#"
              className="text-[14px] text-[#4b5563] hover:text-[#111827] transition-colors"
            >
              Docs
            </Link>
            <Link
              href="#"
              className="text-[14px] text-[#4b5563] hover:text-[#111827] transition-colors"
            >
              Pricing
            </Link>
          </div>

          {/* right */}
          <div className="flex items-center gap-3">
            <Link
              href="/auth/login"
              className="hidden sm:inline-flex text-[14px] text-[#4b5563] border border-gray-200 rounded-lg px-4 py-2 hover:border-gray-300 hover:text-[#111827] transition-colors"
            >
              Log in
            </Link>
            <Link
              href="/auth/login"
              className="text-[14px] text-white bg-[#111827] rounded-full px-5 py-2 hover:bg-[#1f2937] transition-colors"
            >
              Start free
            </Link>
          </div>
        </div>
      </nav>

      {/* ── WHITE HERO ────────────────────────────────────────── */}
      <section className="pt-[160px] pb-24 bg-white">
        <div className="max-w-[1240px] mx-auto px-6">
          {/* pill */}
          <div className="inline-flex items-center gap-2 border border-gray-200 rounded-full px-3.5 py-1.5 mb-8">
            <span className="w-2 h-2 rounded-full bg-orange-400" />
            <span className="text-[12px] text-[#4b5563] font-medium tracking-wide">
              Platform Analytics
            </span>
          </div>

          {/* title */}
          <h1 className="text-[52px] md:text-[72px] font-medium tracking-[-0.03em] text-[#111827] leading-[1.0] max-w-3xl">
            Observe every token.
            <br />
            Govern every decision.
          </h1>

          {/* subtitle */}
          <p className="text-[19px] text-[#4b5563] max-w-xl leading-relaxed mt-6">
            Real-time visibility into agent behavior, token consumption, and
            pipeline health&nbsp;&mdash; with enterprise-grade audit trails.
          </p>

          {/* buttons */}
          <div className="flex flex-wrap items-center gap-4 mt-10">
            <Link
              href="/auth/login"
              className="inline-flex items-center gap-2 text-[15px] text-white bg-[#111827] rounded-full px-7 py-3 hover:bg-[#1f2937] transition-colors"
            >
              Start monitoring
              <ArrowRight className="w-4 h-4" />
            </Link>
            <Link
              href="/admin/apps"
              className="inline-flex items-center gap-2 text-[15px] text-[#111827] border border-gray-200 rounded-full px-7 py-3 hover:border-gray-300 transition-colors"
            >
              View live demo
            </Link>
          </div>
        </div>
      </section>

      {/* ── GIANT METRICS ─────────────────────────────────────── */}
      <section className="mt-20">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-px bg-gray-200">
          {[
            { number: "1.56M", label: "Tokens processed" },
            { number: "586", label: "Agent runs" },
            { number: "94.4%", label: "Success rate" },
            { number: "$3.12", label: "Total spend" },
          ].map((m) => (
            <div key={m.label} className="bg-white p-8 md:p-12">
              <div className="text-[48px] sm:text-[56px] md:text-[72px] font-semibold tracking-tight text-[#111827] leading-none">
                {m.number}
              </div>
              <div className="text-[13px] md:text-[14px] text-gray-500 uppercase tracking-wide mt-3">
                {m.label}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ── STATS DASHBOARD MOCKUP ────────────────────────────── */}
      <section className="py-24 bg-white">
        <div className="max-w-[1100px] mx-auto px-6">
          <div className="rounded-[24px] border border-gray-200 bg-white shadow-[0_20px_60px_-10px_rgba(0,0,0,0.08)] overflow-hidden">
            {/* top bar */}
            <div className="h-14 border-b border-gray-100 px-6 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <span className="text-[13px] text-gray-400">
                  Admin{" "}
                  <span className="mx-1 text-gray-300">&rsaquo;</span> Stats
                </span>
                <span className="text-[18px] font-semibold text-[#111827]">
                  Usage
                </span>
              </div>
              <div className="hidden sm:flex items-center gap-1">
                {["7 days", "30 days", "90 days", "Custom"].map((p) => (
                  <button
                    key={p}
                    className={`text-[12px] px-3 py-1.5 rounded-lg transition-colors ${
                      p === "30 days"
                        ? "bg-gray-900 text-white"
                        : "text-gray-500 hover:bg-gray-100"
                    }`}
                  >
                    {p}
                  </button>
                ))}
              </div>
            </div>

            {/* tab bar */}
            <div className="flex items-center gap-6 px-6 border-b border-gray-100">
              {["Overview", "RAG", "Agents", "Resources"].map((tab) => (
                <button
                  key={tab}
                  className={`py-3 text-[13px] font-medium transition-colors ${
                    tab === "Overview"
                      ? "text-[#111827] border-b-2 border-black"
                      : "text-gray-400 hover:text-gray-600"
                  }`}
                >
                  {tab}
                </button>
              ))}
            </div>

            {/* stats cards row */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 p-6">
              {[
                { title: "Users", value: "12", sub: "12 new" },
                { title: "Active Users", value: "11", sub: "12 total" },
                {
                  title: "Tokens",
                  value: "1561.4K",
                  sub: "$3.12 spend",
                },
                {
                  title: "Agent Runs",
                  value: "586",
                  sub: "33 failed",
                  warn: true,
                },
              ].map((c) => (
                <div
                  key={c.title}
                  className="border border-gray-200 rounded-xl p-4"
                >
                  <div className="text-[11px] text-gray-400 uppercase tracking-wide mb-2">
                    {c.title}
                  </div>
                  <div className="text-[24px] font-semibold text-[#111827] leading-tight">
                    {c.value}
                  </div>
                  <div
                    className={`text-[12px] mt-1 ${
                      c.warn ? "text-amber-500" : "text-gray-500"
                    }`}
                  >
                    {c.sub}
                  </div>
                </div>
              ))}
            </div>

            {/* charts area + side summary */}
            <div className="grid md:grid-cols-[1fr_1fr_220px] gap-6 px-6 pb-6">
              {/* left chart — DAU */}
              <div className="rounded-xl border border-gray-200 p-4">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-[14px] font-semibold text-[#111827]">
                    Daily Active Users
                  </span>
                  <span className="text-[11px] text-gray-400 bg-gray-100 rounded px-2 py-0.5">
                    30d
                  </span>
                </div>
                <div className="text-[32px] font-semibold text-[#111827] leading-tight">
                  11
                </div>
                <div className="text-[12px] text-gray-400 mb-4">
                  Active in period
                </div>
                {/* bar chart */}
                <div className="flex items-end gap-[3px] h-[90px]">
                  {dauBars.map((v, i) => (
                    <div
                      key={i}
                      className="flex-1 rounded-t-sm bg-emerald-400/80"
                      style={{ height: `${(v / 11) * 100}%` }}
                    />
                  ))}
                </div>
                <div className="flex items-center justify-between mt-2">
                  <span className="text-[10px] text-gray-400">2026-02-22</span>
                  <span className="text-[10px] text-gray-400">2026-03-23</span>
                </div>
              </div>

              {/* right chart — Spend */}
              <div className="rounded-xl border border-gray-200 p-4">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-[14px] font-semibold text-[#111827]">
                    Spend Trend
                  </span>
                  <span className="text-[11px] text-gray-400 bg-gray-100 rounded px-2 py-0.5">
                    30d
                  </span>
                </div>
                <div className="text-[32px] font-semibold text-[#111827] leading-tight">
                  $3.12
                </div>
                <div className="text-[12px] text-gray-400 mb-4">
                  Estimated spend
                </div>
                {/* bar chart */}
                <div className="flex items-end gap-[3px] h-[90px]">
                  {spendBars.map((v, i) => (
                    <div
                      key={i}
                      className="flex-1 rounded-t-sm bg-amber-400/80"
                      style={{ height: `${v === 0 ? 0 : (v / 10) * 100}%` }}
                    />
                  ))}
                </div>
                <div className="flex items-center justify-between mt-2">
                  <span className="text-[10px] text-gray-400">2026-02-22</span>
                  <span className="text-[10px] text-gray-400">2026-03-23</span>
                </div>
              </div>

              {/* side summary */}
              <div className="hidden md:flex flex-col gap-4">
                {/* token usage mini chart */}
                <div className="rounded-xl border border-gray-200 p-4">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-[12px] text-gray-500 font-medium">
                      Token Usage
                    </span>
                    <span className="text-[10px] text-gray-400 bg-gray-100 rounded px-1.5 py-0.5">
                      30d
                    </span>
                  </div>
                  <div className="text-[22px] font-semibold text-[#111827] leading-tight">
                    1561.4K
                  </div>
                  {/* sparkline */}
                  <div className="flex items-end gap-[2px] h-[32px] mt-3">
                    {tokenSparkline.map((v, i) => (
                      <div
                        key={i}
                        className="flex-1 rounded-t-sm bg-violet-400/70"
                        style={{
                          height: `${v === 0 ? 0 : (v / 16) * 100}%`,
                        }}
                      />
                    ))}
                  </div>
                </div>

                {/* period summary */}
                <div className="rounded-xl border border-gray-200 p-4 flex-1">
                  <div className="text-[12px] text-gray-500 font-medium mb-3">
                    Period Summary
                  </div>
                  <div className="space-y-2.5">
                    {[
                      { label: "Total chats", value: "744" },
                      { label: "Avg msg/user", value: "30.3" },
                      { label: "Pipeline jobs", value: "6" },
                    ].map((row) => (
                      <div
                        key={row.label}
                        className="flex items-center justify-between"
                      >
                        <span className="text-[12px] text-gray-500">
                          {row.label}
                        </span>
                        <span className="text-[13px] font-medium text-[#111827]">
                          {row.value}
                        </span>
                      </div>
                    ))}
                    <div className="flex items-center justify-between">
                      <span className="text-[12px] text-gray-500">
                        Agent success
                      </span>
                      <span className="flex items-center gap-1.5 text-[13px] font-medium text-[#111827]">
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                        94.4%
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── GOVERNANCE SECTION ────────────────────────────────── */}
      <section className="py-24 bg-gray-50/50 border-t border-gray-100">
        <div className="max-w-[1100px] mx-auto px-6 grid md:grid-cols-2 gap-16 items-start">
          {/* left text */}
          <div>
            <h2 className="text-[36px] font-medium tracking-[-0.02em] text-[#111827] leading-[1.15]">
              Enterprise governance,
              <br />
              built in
            </h2>
            <p className="text-[16px] text-[#4b5563] leading-relaxed mt-5 max-w-md">
              Multi-organization isolation, complete audit trails, and role-based
              access control&nbsp;&mdash; designed for organizations that take AI
              operations seriously.
            </p>
            <div className="mt-8 space-y-4">
              {[
                "Multi-organization data isolation at the infrastructure level",
                "Complete audit trails for every agent action and token",
                "Role-based access control across teams and agents",
                "Configurable guardrails and policy boundaries",
              ].map((item) => (
                <div key={item} className="flex items-start gap-3">
                  <span className="w-1.5 h-1.5 rounded-full bg-gray-400 mt-[9px] shrink-0" />
                  <span className="text-[15px] text-[#374151] leading-relaxed">
                    {item}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* right visual */}
          <div className="rounded-[24px] border border-gray-200 bg-white p-6 shadow-sm">
            <div className="text-[16px] font-semibold text-[#111827] mb-5">
              Security &amp; Org
            </div>
            <div className="space-y-4">
              {[
                {
                  organization: "Acme Corp",
                  badge: "Isolated",
                  badgeColor: "bg-emerald-50 text-emerald-600",
                  agents: [
                    "Customer Service",
                    "Platform Architect",
                    "PRICO Agent",
                  ],
                },
                {
                  organization: "Beta Inc",
                  badge: "Isolated",
                  badgeColor: "bg-emerald-50 text-emerald-600",
                  agents: ["Coding Agent", "Data Analyst"],
                },
                {
                  organization: "Demo",
                  badge: "Sandbox",
                  badgeColor: "bg-amber-50 text-amber-600",
                  agents: ["Demo Agent"],
                },
              ].map((row) => (
                <div
                  key={row.organization}
                  className="rounded-xl border border-gray-100 p-4"
                >
                  <div className="flex items-center justify-between mb-3">
                    <span className="text-[14px] font-medium text-[#111827]">
                      Organization: {row.organization}
                    </span>
                    <span
                      className={`text-[11px] font-medium rounded-full px-2.5 py-0.5 ${row.badgeColor}`}
                    >
                      {row.badge}
                    </span>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {row.agents.map((a) => (
                      <span
                        key={a}
                        className="text-[12px] text-gray-500 bg-gray-50 border border-gray-100 rounded-md px-2.5 py-1"
                      >
                        {a}
                      </span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
            <p className="text-[12px] text-gray-400 mt-5 leading-relaxed">
              All data, traces, and model access fully segregated per organization.
            </p>
          </div>
        </div>
      </section>

      {/* ── PIPELINE HEALTH SECTION ───────────────────────────── */}
      <section className="py-24 bg-white">
        <div className="max-w-[1100px] mx-auto px-6">
          <div className="text-center mb-16">
            <h2 className="text-[36px] font-medium tracking-[-0.02em] text-[#111827]">
              From ingestion to retrieval
            </h2>
            <p className="text-[17px] text-[#4b5563] mt-4 max-w-lg mx-auto leading-relaxed">
              Fully managed RAG pipelines with visibility into every stage of
              your knowledge base.
            </p>
          </div>

          {/* flow diagram */}
          <div className="flex flex-col md:flex-row items-stretch justify-center gap-0 max-w-[900px] mx-auto">
            {[
              {
                stage: "01",
                name: "Ingest",
                desc: "Upload documents, connect data sources",
                stat: "6 pipeline jobs",
              },
              {
                stage: "02",
                name: "Chunk",
                desc: "Split content into retrievable passages",
                stat: null,
              },
              {
                stage: "03",
                name: "Embed",
                desc: "Generate vector embeddings with configurable models",
                stat: null,
              },
              {
                stage: "04",
                name: "Retrieve",
                desc: "Semantic search across your knowledge base",
                stat: null,
              },
            ].map((step, i) => (
              <div key={step.stage} className="flex items-center">
                <div className="border border-gray-200 rounded-xl p-5 bg-white w-full md:w-[200px] flex flex-col">
                  <span className="text-[11px] text-gray-400 uppercase tracking-wide">
                    Stage {step.stage}
                  </span>
                  <span className="text-[16px] font-semibold text-[#111827] mt-1.5">
                    {step.name}
                  </span>
                  <span className="text-[13px] text-gray-500 leading-snug mt-1.5 flex-1">
                    {step.desc}
                  </span>
                  {step.stat && (
                    <span className="text-[11px] text-emerald-600 bg-emerald-50 rounded-md px-2 py-0.5 mt-3 self-start">
                      {step.stat}
                    </span>
                  )}
                </div>
                {i < 3 && (
                  <div className="hidden md:flex items-center justify-center w-8 shrink-0 text-gray-300">
                    <svg
                      width="20"
                      height="12"
                      viewBox="0 0 20 12"
                      fill="none"
                      className="text-gray-300"
                    >
                      <path
                        d="M0 6H18M18 6L13 1M18 6L13 11"
                        stroke="currentColor"
                        strokeWidth="1.5"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </svg>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── CTA SECTION ───────────────────────────────────────── */}
      <section className="py-32 bg-white border-t border-gray-100">
        <div className="max-w-[1100px] mx-auto px-6 text-center">
          <h2 className="text-[36px] md:text-[44px] font-medium tracking-[-0.02em] text-[#111827] leading-[1.1]">
            See your AI operations clearly.
          </h2>
          <p className="text-[17px] text-[#4b5563] mt-5 max-w-md mx-auto leading-relaxed">
            Start monitoring agent performance, token usage, and pipeline health
            in minutes.
          </p>
          <div className="flex flex-wrap items-center justify-center gap-4 mt-10">
            <Link
              href="/auth/login"
              className="inline-flex items-center gap-2 text-[15px] text-white bg-[#111827] rounded-full px-7 py-3 hover:bg-[#1f2937] transition-colors"
            >
              Start monitoring
              <ArrowRight className="w-4 h-4" />
            </Link>
            <Link
              href="/admin/apps"
              className="inline-flex items-center gap-2 text-[15px] text-[#111827] border border-gray-200 rounded-full px-7 py-3 hover:border-gray-300 transition-colors"
            >
              View live demo
            </Link>
          </div>
        </div>
      </section>

      {/* ── FOOTER ────────────────────────────────────────────── */}
      <footer className="border-t border-gray-100 py-10">
        <div className="max-w-[1100px] mx-auto px-6 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2.5">
            <div className="w-6 h-6 bg-[#111827] rounded-[4px] flex items-center justify-center text-white text-[11px] font-bold leading-none">
              T
            </div>
            <span className="text-[13px] text-gray-400">
              Talmudpedia &copy; 2026
            </span>
          </div>
          <div className="flex items-center gap-6">
            <Link
              href="#"
              className="text-[13px] text-gray-400 hover:text-gray-600 transition-colors"
            >
              Privacy
            </Link>
            <Link
              href="#"
              className="text-[13px] text-gray-400 hover:text-gray-600 transition-colors"
            >
              Terms
            </Link>
            <Link
              href="#"
              className="text-[13px] text-gray-400 hover:text-gray-600 transition-colors"
            >
              Docs
            </Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
