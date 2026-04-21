"use client";

import Link from "next/link";
import { ChevronDown, ArrowRight, Search, Plus } from "lucide-react";

const agents = [
  {
    name: "customer service",
    slug: "test",
    description: "",
    threads: 18,
    version: 3,
    status: "PUBLISHED" as const,
    bars: [3, 5, 2, 7, 4, 6],
  },
  {
    name: "PRICO Demo Agent",
    slug: "prico-demo-agent",
    description:
      "Standalone PRICO demo agent backed by local HTTP tools.",
    threads: 49,
    version: 14,
    status: "PUBLISHED" as const,
    bars: [6, 4, 8, 3, 7, 5],
  },
  {
    name: "Artifact Coding Agent",
    slug: "artifact-coding-agent",
    description:
      "Public platform artifact coding agent for live artifact draft editing from th...",
    threads: 69,
    version: 3,
    status: "PUBLISHED" as const,
    bars: [4, 7, 5, 8, 6, 3],
  },
  {
    name: "Platform Architect",
    slug: "platform-architect",
    description:
      "Dynamic single-agent platform architect runtime using Control Pla...",
    threads: 71,
    version: 7,
    status: "PUBLISHED" as const,
    bars: [5, 8, 4, 6, 7, 9],
  },
];

const prompts = [
  {
    name: "useful prompt",
    version: 2,
    scope: "organization",
    preview:
      "## Role and scope\nYou are a read-only treasury/copilot-style agent for exactly one selected PRICO...",
  },
  {
    name: "customer service instruction",
    version: 2,
    scope: "organization",
    preview:
      "## Preferred widget usage patterns\n- For bank or currency concentration, prefer pie or bar...",
  },
  {
    name: "prico poc agent",
    version: 13,
    scope: "organization",
    preview:
      "You are the PRICO Client Exposure Copilot demo agent.\n## Role and scope\nYou are a read-only...",
  },
];

const metrics = [
  { value: "586", label: "Agent executions" },
  { value: "94.4%", label: "Success rate" },
  { value: "5", label: "Published agents" },
  { value: "207", label: "Total threads" },
];

export function LandingV10() {
  return (
    <div className="min-h-screen bg-white font-sans overflow-x-hidden selection:bg-gray-900/10 selection:text-gray-900">
      {/* ── Fixed Nav ── */}
      <nav className="fixed top-0 z-50 w-full bg-white/95 backdrop-blur border-b border-gray-100 h-16 flex items-center">
        <div className="w-full max-w-[1240px] mx-auto px-6 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2.5">
            <div className="w-7 h-7 bg-black text-white font-bold text-[14px] flex items-center justify-center rounded-sm">
              T
            </div>
            <span className="font-bold text-xl tracking-tight text-[#111827]">
              Talmudpedia
            </span>
          </Link>

          <div className="hidden md:flex items-center gap-7 text-[14px] font-medium text-[#4b5563]">
            <button className="flex items-center gap-1 hover:text-[#111827] transition-colors">
              Platform <ChevronDown className="w-3.5 h-3.5 opacity-60" />
            </button>
            <Link href="/admin/agents" className="hover:text-[#111827] transition-colors">
              Agents
            </Link>
            <Link href="/admin/apps" className="hover:text-[#111827] transition-colors">
              Apps
            </Link>
            <Link href="#" className="hover:text-[#111827] transition-colors">
              Docs
            </Link>
            <Link href="#" className="hover:text-[#111827] transition-colors">
              Pricing
            </Link>
          </div>

          <div className="flex items-center gap-3">
            <Link
              href="/auth/login"
              className="hidden sm:block text-[14px] font-medium text-[#4b5563] border border-gray-200 rounded-full px-4 py-2 hover:border-gray-300 hover:text-[#111827] transition-colors"
            >
              Log in
            </Link>
            <Link
              href="/auth/login"
              className="px-4 py-2 bg-black text-white text-[14px] font-medium rounded-full hover:bg-gray-800 transition-colors"
            >
              Get started
            </Link>
          </div>
        </div>
      </nav>

      {/* ── Hero Section — White, dot-grid background ── */}
      <section className="relative bg-white py-32 pt-[140px] px-6 flex flex-col items-center text-center overflow-hidden">
        {/* Dot grid */}
        <div className="absolute inset-0 bg-[radial-gradient(#e5e7eb_1.5px,transparent_1.5px)] bg-[size:24px_24px] opacity-50 pointer-events-none" />

        <div className="relative z-10 w-full max-w-[1000px] mx-auto flex flex-col items-center">
          {/* Pill badge */}
          <div className="inline-flex items-center gap-2 border border-gray-200 bg-white rounded-full px-3 py-1 mb-8 shadow-sm">
            <span className="flex h-2 w-2 rounded-full bg-emerald-500" />
            <span className="text-[12px] font-medium text-[#4b5563] tracking-wide">
              Agents
            </span>
          </div>

          <h1 className="text-[52px] md:text-[64px] font-medium tracking-tight text-[#111827] leading-[1.05] mb-6">
            Deploy intelligent agents
            <br />
            in minutes, not months.
          </h1>

          <p className="text-[18px] text-[#4b5563] max-w-2xl leading-relaxed mb-10">
            Talmudpedia&apos;s visual agent builder lets you compose reasoning
            graphs, connect knowledge sources, and publish production-ready
            agents with built-in governance.
          </p>

          <div className="flex flex-col sm:flex-row items-center gap-4 w-full justify-center">
            <Link
              href="/auth/login"
              className="w-full sm:w-auto px-7 py-3.5 bg-black text-white text-[14px] font-medium rounded-full hover:bg-gray-800 transition-colors flex items-center justify-center gap-2 group"
            >
              Create your first agent
              <ArrowRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
            </Link>
            <Link
              href="/admin/agents"
              className="w-full sm:w-auto px-7 py-3.5 bg-white border border-gray-200 text-[#111827] text-[14px] font-medium rounded-full hover:border-gray-300 transition-colors flex items-center justify-center"
            >
              Explore the platform
            </Link>
          </div>
        </div>

        {/* ── Hero Product Mockup — Agent Cards Grid ── */}
        <div className="relative z-10 w-full max-w-[1000px] mx-auto mt-20">
          <div className="rounded-[24px] border border-gray-200 bg-white shadow-[0_40px_100px_-20px_rgba(0,0,0,0.08)] p-6 md:p-8">
            {/* Top bar */}
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-[18px] font-semibold text-[#111827]">
                Agents
              </h2>
              <div className="flex items-center gap-3">
                <div className="hidden sm:flex items-center gap-2 border border-gray-200 rounded-lg px-3 py-2 text-[13px] text-gray-400 w-[200px]">
                  <Search className="w-3.5 h-3.5 text-gray-300" />
                  Search agents...
                </div>
                <button className="flex items-center gap-1.5 bg-black text-white text-[13px] font-medium rounded-lg px-3.5 py-2 hover:bg-gray-800 transition-colors">
                  <Plus className="w-3.5 h-3.5" />
                  New Agent
                </button>
              </div>
            </div>

            {/* Agent cards grid */}
            <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-4">
              {agents.map((agent) => (
                <div
                  key={agent.slug}
                  className="rounded-xl border border-gray-200 p-4 hover:border-gray-300 transition-colors cursor-pointer group"
                >
                  {/* Status */}
                  <div className="flex items-center gap-1.5 mb-3">
                    <span
                      className={`flex h-1.5 w-1.5 rounded-full ${
                        agent.status === "PUBLISHED"
                          ? "bg-emerald-500"
                          : "bg-gray-300"
                      }`}
                    />
                    <span
                      className={`text-[11px] uppercase tracking-wide font-semibold ${
                        agent.status === "PUBLISHED"
                          ? "text-emerald-600"
                          : "text-gray-400"
                      }`}
                    >
                      {agent.status}
                    </span>
                  </div>

                  {/* Name + slug */}
                  <div className="text-[15px] font-semibold text-[#111827] leading-snug">
                    {agent.name}
                  </div>
                  <div className="text-[12px] text-gray-400 font-mono mt-0.5">
                    {agent.slug}
                  </div>

                  {/* Description */}
                  {agent.description ? (
                    <p className="text-[13px] text-gray-500 mt-2 line-clamp-2 leading-relaxed">
                      {agent.description}
                    </p>
                  ) : (
                    <p className="text-[13px] text-gray-300 mt-2 italic">
                      No description
                    </p>
                  )}

                  {/* Threads */}
                  <div className="mt-4 pt-3 border-t border-gray-100">
                    <div className="text-[10px] uppercase tracking-widest text-gray-400 mb-1">
                      Threads
                    </div>
                    <div className="text-[20px] font-semibold text-[#111827]">
                      {agent.threads}
                    </div>
                  </div>

                  {/* Mini bar chart */}
                  <div className="flex items-end gap-1 h-8 mt-2">
                    {agent.bars.map((h, i) => (
                      <div
                        key={i}
                        className="flex-1 bg-violet-500/20 rounded-sm group-hover:bg-violet-500/30 transition-colors"
                        style={{ height: `${(h / 9) * 100}%` }}
                      />
                    ))}
                  </div>

                  {/* Footer */}
                  <div className="flex items-center justify-between mt-3 text-[11px] text-gray-400">
                    <span>v{agent.version}</span>
                    <div className="flex items-center gap-2">
                      <span>3/23/2026</span>
                      <ArrowRight className="w-3 h-3 opacity-0 group-hover:opacity-100 transition-opacity" />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Floating card below mockup */}
          <div className="flex justify-center">
            <div className="relative -mt-6 bg-[#111] rounded-2xl px-6 py-4 shadow-2xl border border-gray-800 flex items-center gap-5 max-w-lg z-20">
              <div className="flex items-center gap-4 min-w-0">
                <div className="shrink-0 w-10 h-10 rounded-xl bg-white/10 flex items-center justify-center">
                  <div className="w-4 h-4 rounded-sm bg-violet-400" />
                </div>
                <div className="min-w-0">
                  <div className="text-[14px] font-semibold text-white">
                    Agent Orchestration
                  </div>
                  <div className="text-[12px] text-white/50 leading-relaxed">
                    Compose, version, and deploy agents with visual graphs.
                  </div>
                </div>
              </div>
              <Link
                href="/admin/agents"
                className="shrink-0 text-[13px] font-medium bg-white text-black px-4 py-2 rounded-full hover:bg-gray-100 transition-colors"
              >
                Learn more
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* ── Graph Builder Section ── */}
      <section className="py-24 bg-gray-50/50 border-t border-gray-100 px-6">
        <div className="w-full max-w-[1100px] mx-auto grid lg:grid-cols-2 gap-16 items-center">
          {/* Left: Graph mockup */}
          <div className="rounded-[24px] border border-gray-200 bg-white p-6 aspect-[4/3] relative overflow-hidden">
            {/* Tabs */}
            <div className="flex items-center gap-1 mb-8">
              <button className="text-[13px] font-medium text-[#111827] bg-gray-100 rounded-lg px-3.5 py-1.5">
                Build
              </button>
              <button className="text-[13px] font-medium text-gray-400 rounded-lg px-3.5 py-1.5">
                Execute
              </button>
            </div>

            {/* Left panel hint */}
            <div className="absolute left-0 top-[72px] bottom-0 w-[52px] border-r border-gray-100 bg-gray-50/80">
              <div className="px-1.5 pt-4">
                <div className="text-[7px] uppercase tracking-widest text-gray-400 font-semibold mb-3 text-center">
                  Nodes
                </div>
                {["S", "A", "C", "L", "T", "R"].map((letter) => (
                  <div
                    key={letter}
                    className="w-7 h-7 mx-auto mb-1.5 rounded-md border border-gray-200 bg-white flex items-center justify-center text-[10px] font-mono text-gray-400"
                  >
                    {letter}
                  </div>
                ))}
              </div>
            </div>

            {/* Canvas with connected nodes */}
            <div className="ml-[52px] h-[calc(100%-60px)] flex items-center justify-center relative">
              {/* Connection lines */}
              <svg
                className="absolute inset-0 w-full h-full pointer-events-none"
                preserveAspectRatio="none"
              >
                <line
                  x1="27%"
                  y1="50%"
                  x2="43%"
                  y2="50%"
                  stroke="#d1d5db"
                  strokeWidth="1.5"
                  strokeDasharray="6 4"
                />
                <line
                  x1="57%"
                  y1="50%"
                  x2="73%"
                  y2="50%"
                  stroke="#d1d5db"
                  strokeWidth="1.5"
                  strokeDasharray="6 4"
                />
              </svg>

              {/* Start node */}
              <div className="relative flex flex-col items-center z-10">
                <div className="text-[9px] uppercase tracking-widest text-gray-400 font-semibold mb-2">
                  Control
                </div>
                <div className="rounded-xl border-2 border-dashed border-gray-300 px-6 py-3 bg-white">
                  <div className="text-[13px] font-medium text-gray-500">
                    Start
                  </div>
                </div>
              </div>

              {/* Spacer */}
              <div className="w-16 lg:w-20" />

              {/* Agent node */}
              <div className="relative flex flex-col items-center z-10">
                <div className="text-[9px] uppercase tracking-widest text-emerald-600 font-semibold mb-2">
                  Reasoning
                </div>
                <div className="rounded-xl border border-gray-200 bg-white shadow-sm px-6 py-3 border-l-[3px] border-l-emerald-500">
                  <div className="text-[13px] font-semibold text-[#111827]">
                    Agent
                  </div>
                  <div className="text-[10px] text-gray-400 mt-0.5">
                    platform-architect
                  </div>
                </div>
              </div>

              {/* Spacer */}
              <div className="w-16 lg:w-20" />

              {/* End node */}
              <div className="relative flex flex-col items-center z-10">
                <div className="text-[9px] uppercase tracking-widest text-gray-400 font-semibold mb-2">
                  Control
                </div>
                <div className="rounded-xl border-2 border-dashed border-gray-300 px-6 py-3 bg-white">
                  <div className="text-[13px] font-medium text-gray-500">
                    End
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Right: Text content */}
          <div>
            <h2 className="text-[36px] font-medium tracking-tight text-[#111827] leading-tight mb-5">
              From graph to production
            </h2>
            <p className="text-[16px] text-[#4b5563] leading-relaxed mb-10">
              The visual builder turns agent logic into composable graphs. Drag
              reasoning, retrieval, and tool nodes onto the canvas, wire them
              together, and publish a versioned agent — all without writing
              orchestration code.
            </p>

            <div className="space-y-0">
              {[
                {
                  title: "Drag-and-drop node composition",
                  desc: "Arrange Start, Agent, Classify, LLM, Tool, Retrieval, and Vector Search nodes on an infinite canvas.",
                },
                {
                  title: "Built-in reasoning, retrieval, and tool nodes",
                  desc: "Each node type encapsulates a production pattern — from chain-of-thought to RAG to external API calls.",
                },
                {
                  title: "One-click publish with version tracking",
                  desc: "Every publish creates an immutable version. Roll back instantly or promote drafts to production.",
                },
              ].map((item, i) => (
                <div
                  key={i}
                  className="py-4 border-b border-gray-100 last:border-b-0"
                >
                  <div className="text-[15px] font-medium text-[#111827]">
                    {item.title}
                  </div>
                  <div className="text-[13px] text-gray-500 mt-1 leading-relaxed">
                    {item.desc}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ── Prompt Library Section ── */}
      <section className="py-24 bg-white border-t border-gray-100 px-6">
        <div className="w-full max-w-[900px] mx-auto">
          <div className="text-center mb-14">
            <h2 className="text-[36px] font-medium tracking-tight text-[#111827] leading-tight mb-4">
              Shared prompt library
            </h2>
            <p className="text-[16px] text-[#4b5563] max-w-xl mx-auto leading-relaxed">
              Write prompts once and reference them across agents. Version
              history, organization-scoped access, and inline previews keep your
              instructions consistent and auditable.
            </p>
          </div>

          <div className="grid md:grid-cols-3 gap-6">
            {prompts.map((prompt) => (
              <div
                key={prompt.name}
                className="rounded-xl border border-gray-200 p-5 hover:border-gray-300 transition-colors"
              >
                {/* Status */}
                <div className="flex items-center gap-1.5">
                  <span className="flex h-1.5 w-1.5 rounded-full bg-emerald-500" />
                  <span className="text-[11px] uppercase tracking-wide font-semibold text-emerald-600">
                    Active
                  </span>
                </div>

                {/* Name */}
                <div className="text-[16px] font-semibold text-[#111827] mt-3">
                  {prompt.name}
                </div>

                {/* Preview */}
                <p className="text-[13px] text-gray-500 mt-2 line-clamp-3 leading-relaxed font-mono">
                  {prompt.preview}
                </p>

                {/* Footer */}
                <div className="flex items-center justify-between mt-4 pt-3 border-t border-gray-100">
                  <div className="flex items-center gap-2 text-[12px] text-gray-400">
                    <span className="font-medium">v{prompt.version}</span>
                    <span className="text-gray-200">|</span>
                    <span>{prompt.scope}</span>
                  </div>
                  <button className="text-gray-300 hover:text-gray-500 transition-colors">
                    <svg
                      width="14"
                      height="14"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    >
                      <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
                    </svg>
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Metrics Strip ── */}
      <section className="py-12 bg-[#0a0a0a] px-6">
        <div className="w-full max-w-[900px] mx-auto grid grid-cols-2 md:grid-cols-4 gap-8">
          {metrics.map((m) => (
            <div key={m.label} className="text-center">
              <div className="text-[36px] font-semibold text-white">
                {m.value}
              </div>
              <div className="text-[13px] text-white/50 mt-1">{m.label}</div>
            </div>
          ))}
        </div>
      </section>

      {/* ── CTA Section ── */}
      <section className="py-32 bg-white px-6">
        <div className="bg-[#fafafa] rounded-[32px] border border-gray-200 max-w-4xl mx-auto p-12 md:p-20 text-center">
          <h2 className="text-[40px] font-medium tracking-tight text-[#111827] leading-tight mb-5">
            Ready to orchestrate?
          </h2>
          <p className="text-[16px] text-[#4b5563] max-w-lg mx-auto leading-relaxed mb-10">
            Start with a single agent, scale to a catalog. Talmudpedia handles
            versioning, governance, and runtime so you can focus on the logic
            that matters.
          </p>
          <div className="flex flex-col sm:flex-row items-center gap-4 justify-center">
            <Link
              href="/auth/login"
              className="w-full sm:w-auto px-7 py-3.5 bg-black text-white text-[14px] font-medium rounded-full hover:bg-gray-800 transition-colors flex items-center justify-center gap-2 group"
            >
              Get started free
              <ArrowRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
            </Link>
            <Link
              href="/admin/agents"
              className="w-full sm:w-auto px-7 py-3.5 bg-white border border-gray-200 text-[#111827] text-[14px] font-medium rounded-full hover:border-gray-300 transition-colors flex items-center justify-center"
            >
              View live agents
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
}
