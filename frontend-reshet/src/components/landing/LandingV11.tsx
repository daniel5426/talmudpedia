"use client";

import Link from "next/link";
import { ArrowRight, ChevronDown } from "lucide-react";

/* ─────────────────────────────────────────────
   Node palette data (mirrors real builder)
   ───────────────────────────────────────────── */
const NODE_SECTIONS = [
  {
    label: "CONTROL FLOW",
    items: [
      { name: "Start", accent: null },
      { name: "End", accent: null },
    ],
  },
  {
    label: "REASONING",
    items: [
      { name: "Agent", accent: "#22c55e" },
      { name: "Classify", accent: "#a78bfa" },
      { name: "LLM", accent: "#60a5fa" },
    ],
  },
  {
    label: "ACTIONS",
    items: [
      { name: "Tool", accent: "#f59e0b" },
      { name: "Retrieval", accent: "#f472b6" },
      { name: "Vector Search", accent: "#34d399" },
    ],
  },
] as const;

/* ─────────────────────────────────────────────
   Component
   ───────────────────────────────────────────── */
export function LandingV11() {
  return (
    <div className="min-h-screen font-sans overflow-x-hidden selection:bg-emerald-200/30">
      {/* ── 1. Fixed Nav ─────────────────────────── */}
      <nav className="fixed top-0 z-50 w-full h-16 flex items-center bg-[#0a0a0a]/90 backdrop-blur-xl border-b border-white/5">
        <div className="w-full max-w-[1280px] mx-auto px-6 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2.5">
            <div className="w-6 h-6 bg-white text-black font-medium text-[14px] flex items-center justify-center rounded-[4px]">
              T
            </div>
            <span className="font-medium text-[15px] tracking-tight text-white">
              Talmudpedia
            </span>
          </Link>

          <div className="hidden md:flex items-center gap-8 text-[14px] text-white/50">
            <button className="flex items-center gap-1 hover:text-white/80 transition-colors">
              Platform <ChevronDown className="w-3.5 h-3.5 opacity-60" />
            </button>
            <Link href="#" className="hover:text-white/80 transition-colors">
              Agents
            </Link>
            <Link href="#" className="hover:text-white/80 transition-colors">
              Artifacts
            </Link>
            <Link href="#" className="hover:text-white/80 transition-colors">
              Docs
            </Link>
          </div>

          <div className="flex items-center gap-3">
            <Link
              href="/auth/login"
              className="hidden sm:block text-[13px] font-medium text-white/70 hover:text-white transition-colors px-3 py-2"
            >
              Sign in
            </Link>
            <Link
              href="/admin/agents"
              className="px-4 py-2 bg-white text-black hover:bg-gray-100 text-[13px] font-medium rounded-full transition-colors"
            >
              Start building
            </Link>
          </div>
        </div>
      </nav>

      {/* ── 2. Dark Hero ─────────────────────────── */}
      <section className="relative min-h-[90vh] bg-[#0a0a0a] overflow-hidden">
        {/* Subtle grid */}
        <div className="absolute inset-0 bg-[linear-gradient(to_right,#ffffff05_1px,transparent_1px),linear-gradient(to_bottom,#ffffff05_1px,transparent_1px)] bg-[size:64px_64px] [mask-image:radial-gradient(ellipse_80%_60%_at_50%_20%,black_30%,transparent_100%)]" />

        {/* Ambient glows */}
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[700px] h-[500px] bg-white/[0.02] blur-[140px] rounded-full pointer-events-none" />
        <div className="absolute top-[15%] left-[45%] w-[350px] h-[280px] bg-emerald-500/[0.03] blur-[120px] rounded-full pointer-events-none" />

        {/* Hero text */}
        <div className="relative z-10 pt-[160px] flex flex-col items-center text-center px-6">
          <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full border border-white/10 bg-white/[0.03] backdrop-blur-md mb-8">
            <span className="flex h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
            <span className="text-[12px] font-medium tracking-wide text-white/60 uppercase">
              Visual Agent Builder
            </span>
          </div>

          <h1 className="text-[56px] md:text-[76px] font-medium tracking-tight text-white leading-[0.95] mb-6">
            Drag. Connect.
            <br />
            Deploy.
          </h1>

          <p className="text-[18px] text-white/50 max-w-2xl leading-relaxed mb-10">
            Build production-grade AI agents with a visual graph editor.
            Connect reasoning, retrieval, and tool nodes&nbsp;&mdash; then publish
            with one click.
          </p>

          <div className="flex flex-col sm:flex-row items-center gap-4">
            <Link
              href="/admin/agents"
              className="px-7 py-3.5 bg-white text-black hover:bg-gray-100 text-[14px] font-medium rounded-full transition-colors flex items-center gap-2 group"
            >
              Open the builder
              <ArrowRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
            </Link>
            <Link
              href="#"
              className="px-7 py-3.5 bg-white/5 border border-white/10 hover:bg-white/10 text-white text-[14px] font-medium rounded-full transition-colors backdrop-blur-md"
            >
              Read the docs
            </Link>
          </div>
        </div>

        {/* ── 3. Hero Mockup — The Agent Builder ── */}
        <div className="relative z-10 w-full max-w-[1100px] mx-auto mt-20 px-6">
          <div className="rounded-t-[24px] border border-white/10 border-b-0 bg-[#111]/80 backdrop-blur-2xl shadow-2xl overflow-hidden">
            {/* Toolbar */}
            <div className="h-12 border-b border-white/5 flex items-center px-4">
              {/* Breadcrumb */}
              <div className="flex items-center gap-1.5 text-[13px] text-white/40 flex-1 min-w-0">
                <span className="truncate">Agents</span>
                <span className="text-white/20">/</span>
                <span className="truncate">customer service</span>
                <span className="text-white/20">/</span>
                <span className="text-white/60 truncate">test</span>
              </div>

              {/* Build / Execute tabs */}
              <div className="flex items-center gap-1 mx-auto">
                <button className="relative px-4 py-3 text-[13px] font-medium text-white">
                  Build
                  <span className="absolute bottom-0 left-2 right-2 h-[2px] bg-white rounded-full" />
                </button>
                <button className="px-4 py-3 text-[13px] font-medium text-white/40">
                  Execute
                </button>
              </div>

              {/* Actions */}
              <div className="flex items-center gap-2 flex-1 justify-end">
                <button className="hidden sm:block px-3 py-1.5 text-[12px] font-medium text-white/60 border border-white/10 rounded-lg hover:bg-white/5 transition-colors">
                  Save Draft
                </button>
                <button className="px-3 py-1.5 text-[12px] font-medium text-white bg-emerald-500 hover:bg-emerald-600 rounded-lg transition-colors">
                  Publish
                </button>
              </div>
            </div>

            {/* Content area */}
            <div className="flex">
              {/* Left panel — Node palette */}
              <div className="hidden md:block w-[200px] border-r border-white/5 bg-[#0a0a0a] p-4 flex-shrink-0">
                <div className="text-[10px] uppercase tracking-[0.15em] text-white/30 mb-3 font-medium">
                  Agent Nodes
                </div>

                {/* Search */}
                <div className="relative mb-4">
                  <input
                    readOnly
                    placeholder="Search nodes..."
                    className="w-full bg-white/5 border border-white/5 rounded-lg px-3 py-1.5 text-[12px] text-white/40 placeholder:text-white/25 outline-none cursor-default"
                  />
                </div>

                {NODE_SECTIONS.map((section) => (
                  <div key={section.label} className="mt-4 first:mt-0">
                    <div className="text-[10px] uppercase tracking-[0.15em] text-white/20 mb-2 font-medium">
                      {section.label}
                    </div>
                    {section.items.map((item) => (
                      <div
                        key={item.name}
                        className="flex items-center gap-2 px-2 py-1.5 rounded-md hover:bg-white/5 transition-colors cursor-default"
                      >
                        <div
                          className="w-3 h-3 rounded-[3px] border flex-shrink-0"
                          style={{
                            borderColor: item.accent
                              ? item.accent
                              : "rgba(255,255,255,0.15)",
                            backgroundColor: item.accent
                              ? `${item.accent}20`
                              : "transparent",
                          }}
                        />
                        <span className="text-[13px] text-white/60">
                          {item.name}
                        </span>
                      </div>
                    ))}
                  </div>
                ))}
              </div>

              {/* Canvas */}
              <div className="flex-1 relative bg-[#0d0d0d] min-h-[400px] md:min-h-[420px]">
                {/* Faint dot grid on canvas */}
                <div className="absolute inset-0 bg-[radial-gradient(#ffffff08_1px,transparent_1px)] bg-[size:24px_24px]" />

                {/* Nodes + connections container */}
                <div className="relative z-10 flex items-center justify-center h-full py-16 px-8">
                  <div className="flex items-center gap-0 w-full max-w-[700px]">
                    {/* Node: Start */}
                    <div className="flex flex-col items-center flex-shrink-0">
                      <span className="text-[9px] uppercase tracking-widest text-white/20 mb-1.5 font-medium">
                        Control
                      </span>
                      <div className="rounded-xl border-2 border-dashed border-white/10 px-6 sm:px-8 py-4 bg-white/[0.02] flex items-center gap-2.5">
                        <div className="w-3.5 h-3.5 rounded-[3px] border border-white/15" />
                        <span className="text-[14px] text-white/70 font-medium">
                          Start
                        </span>
                      </div>
                    </div>

                    {/* Connection line 1 */}
                    <div className="flex-1 min-w-[32px] flex items-center relative mx-1">
                      <div className="w-full border-t-2 border-dashed border-white/[0.08]" />
                      <span className="absolute right-0 text-white/20 text-[11px] font-mono -translate-y-[1px]">
                        &rsaquo;
                      </span>
                    </div>

                    {/* Node: Agent */}
                    <div className="flex flex-col items-center flex-shrink-0">
                      <span className="text-[9px] uppercase tracking-widest text-white/20 mb-1.5 font-medium">
                        Reasoning
                      </span>
                      <div className="rounded-xl border border-white/10 border-l-2 border-l-emerald-500 px-6 sm:px-8 py-4 bg-white/[0.03] shadow-lg shadow-emerald-500/5 flex items-center gap-2.5">
                        <div className="w-3.5 h-3.5 rounded-full bg-emerald-500/20 border border-emerald-500/50 flex items-center justify-center">
                          <div className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                        </div>
                        <span className="text-[14px] text-white font-medium">
                          Agent
                        </span>
                      </div>
                    </div>

                    {/* Connection line 2 */}
                    <div className="flex-1 min-w-[32px] flex items-center relative mx-1">
                      <div className="w-full border-t-2 border-dashed border-white/[0.08]" />
                      <span className="absolute right-0 text-white/20 text-[11px] font-mono -translate-y-[1px]">
                        &rsaquo;
                      </span>
                    </div>

                    {/* Node: End */}
                    <div className="flex flex-col items-center flex-shrink-0">
                      <span className="text-[9px] uppercase tracking-widest text-white/20 mb-1.5 font-medium">
                        Control
                      </span>
                      <div className="rounded-xl border-2 border-dashed border-white/10 px-6 sm:px-8 py-4 bg-white/[0.02] flex items-center gap-2.5">
                        <div className="w-3.5 h-3.5 rounded-[3px] border border-white/15" />
                        <span className="text-[14px] text-white/70 font-medium">
                          End
                        </span>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Bottom canvas toolbar */}
                <div className="absolute bottom-4 left-1/2 -translate-x-1/2 flex gap-1.5 z-20">
                  {["+", "\u2212", "\u2b1c", "#"].map((icon, i) => (
                    <div
                      key={i}
                      className="w-8 h-8 bg-white/5 border border-white/5 rounded-lg flex items-center justify-center text-white/30 text-[13px] cursor-default hover:bg-white/10 transition-colors"
                    >
                      {icon}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>

          {/* Bottom gradient fade */}
          <div className="h-32 bg-gradient-to-t from-[#0a0a0a] to-transparent -mt-1 relative z-20" />
        </div>
      </section>

      {/* ── 4. Light Section — "From Builder to Runtime" ── */}
      <section className="bg-white py-28 border-t border-gray-100">
        <div className="max-w-[1100px] mx-auto px-6">
          {/* Section header */}
          <div className="text-center mb-20">
            <h2 className="text-[40px] md:text-[52px] font-medium tracking-tight text-[#111827] leading-[1.05] mb-5">
              What you build is
              <br className="hidden sm:block" /> what runs
            </h2>
            <p className="text-[17px] text-gray-500 max-w-xl mx-auto leading-relaxed">
              The same graph you compose visually becomes the execution plan in
              production. No translation layer, no config drift.
            </p>
          </div>

          {/* 3 horizontal cards — stacked */}
          <div className="flex flex-col gap-6">
            {/* Card 1: Graph Composition */}
            <div className="flex flex-col md:flex-row items-center gap-8 border border-gray-200 rounded-[24px] p-8">
              {/* Mini mockup */}
              <div className="w-full md:w-[300px] flex-shrink-0 bg-gray-50 rounded-2xl p-6 flex items-center justify-center">
                <div className="flex items-center gap-0">
                  <div className="w-4 h-4 rounded-full bg-gray-300" />
                  <div className="w-12 h-[2px] bg-gray-200" />
                  <div className="w-5 h-5 rounded-full bg-emerald-400" />
                  <div className="w-12 h-[2px] bg-gray-200" />
                  <div className="w-5 h-5 rounded-full bg-blue-400" />
                  <div className="w-12 h-[2px] bg-gray-200" />
                  <div className="w-4 h-4 rounded-full bg-gray-300" />
                </div>
              </div>
              {/* Text */}
              <div className="flex-1 min-w-0">
                <h3 className="text-[22px] font-medium text-[#111827] mb-2">
                  Graph Composition
                </h3>
                <p className="text-[15px] text-gray-500 leading-relaxed">
                  Compose multi-step reasoning flows by connecting nodes. Each
                  node encapsulates a single capability&nbsp;&mdash; an LLM call, a
                  retrieval step, a tool invocation. Wire them together and the
                  runtime handles orchestration.
                </p>
              </div>
            </div>

            {/* Card 2: Execution Tracing */}
            <div className="flex flex-col md:flex-row items-center gap-8 border border-gray-200 rounded-[24px] p-8">
              {/* Mini mockup — vertical timeline */}
              <div className="w-full md:w-[300px] flex-shrink-0 bg-gray-50 rounded-2xl p-6">
                <div className="space-y-3">
                  {[
                    { label: "User Input", time: "0ms" },
                    { label: "Graph Router", time: "12ms" },
                    { label: "Knowledge Retrieval", time: "340ms" },
                    { label: "Tool Execution", time: "892ms" },
                  ].map((step, i) => (
                    <div key={i} className="flex items-center gap-3">
                      <div className="flex flex-col items-center">
                        <div
                          className={`w-2.5 h-2.5 rounded-full ${
                            i === 3
                              ? "bg-emerald-400"
                              : "bg-gray-300"
                          }`}
                        />
                        {i < 3 && (
                          <div className="w-[1px] h-3 bg-gray-200 mt-0.5" />
                        )}
                      </div>
                      <div className="flex items-center justify-between flex-1 min-w-0">
                        <span className="text-[12px] text-gray-600 truncate">
                          {step.label}
                        </span>
                        <span className="text-[11px] text-gray-400 font-mono ml-2 flex-shrink-0">
                          {step.time}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
              {/* Text */}
              <div className="flex-1 min-w-0">
                <h3 className="text-[22px] font-medium text-[#111827] mb-2">
                  Execution Tracing
                </h3>
                <p className="text-[15px] text-gray-500 leading-relaxed">
                  Every agent run produces a full execution trace. See exactly
                  which nodes fired, what data flowed between them, and where
                  time was spent. Debug production issues in seconds, not hours.
                </p>
              </div>
            </div>

            {/* Card 3: One-Click Publish */}
            <div className="flex flex-col md:flex-row items-center gap-8 border border-gray-200 rounded-[24px] p-8">
              {/* Mini mockup — version list */}
              <div className="w-full md:w-[300px] flex-shrink-0 bg-gray-50 rounded-2xl p-6">
                <div className="space-y-2">
                  {[
                    { v: "v14", date: "Mar 22, 2026", active: true },
                    { v: "v13", date: "Mar 18, 2026", active: false },
                    { v: "v12", date: "Mar 11, 2026", active: false },
                  ].map((ver) => (
                    <div
                      key={ver.v}
                      className={`flex items-center justify-between px-3 py-2 rounded-lg ${
                        ver.active ? "bg-white shadow-sm border border-gray-100" : ""
                      }`}
                    >
                      <div className="flex items-center gap-2.5">
                        <span className="text-[13px] font-mono font-medium text-gray-700">
                          {ver.v}
                        </span>
                        <span className="text-[11px] text-gray-400">
                          {ver.date}
                        </span>
                      </div>
                      {ver.active && (
                        <span className="text-[10px] font-medium uppercase tracking-wider text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded-full">
                          Active
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              </div>
              {/* Text */}
              <div className="flex-1 min-w-0">
                <h3 className="text-[22px] font-medium text-[#111827] mb-2">
                  One-Click Publish
                </h3>
                <p className="text-[15px] text-gray-500 leading-relaxed">
                  Every deployment is versioned and immutable. Roll back to any
                  previous version instantly. Promote from staging to production
                  with a single click&nbsp;&mdash; no CI pipeline required.
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── 5. Code Artifacts Section ─────────── */}
      <section className="py-24 bg-gray-50/50">
        <div className="max-w-[1100px] mx-auto px-6">
          <div className="flex flex-col lg:flex-row items-center gap-12 lg:gap-16">
            {/* Left — text */}
            <div className="flex-1 min-w-0">
              <h2 className="text-[36px] md:text-[44px] font-medium tracking-tight text-[#111827] leading-[1.1] mb-5">
                Extend with
                <br />
                code artifacts
              </h2>
              <p className="text-[16px] text-gray-500 leading-relaxed mb-8 max-w-md">
                Write custom Python functions, tool integrations, and data
                transforms directly in the platform. Each artifact lives in a
                versioned file tree&nbsp;&mdash; test locally, deploy globally.
              </p>

              {/* File tree hint */}
              <div className="inline-flex flex-col gap-1 text-[13px] font-mono text-gray-400">
                <span className="text-gray-600 font-medium">worker_roundtrip/</span>
                <span className="ml-4">main.py</span>
                <span className="ml-4">module_1.py</span>
                <span className="ml-4">module_2.py</span>
                <span className="ml-4">module_3.py</span>
              </div>
            </div>

            {/* Right — Code editor mockup */}
            <div className="w-full lg:w-[520px] flex-shrink-0">
              <div className="rounded-[20px] border border-gray-200 bg-white shadow-lg overflow-hidden">
                {/* Title bar */}
                <div className="flex items-center gap-3 px-4 py-3 bg-gray-50 border-b border-gray-100">
                  <div className="flex gap-1.5">
                    <div className="w-3 h-3 rounded-full bg-[#ff5f57]" />
                    <div className="w-3 h-3 rounded-full bg-[#febc2e]" />
                    <div className="w-3 h-3 rounded-full bg-[#28c840]" />
                  </div>
                  <span className="text-[12px] text-gray-400 ml-2">
                    main.py
                  </span>
                </div>

                {/* File tabs */}
                <div className="flex border-b border-gray-100 bg-gray-50/50">
                  {["main.py", "module_1.py", "module_2.py"].map((tab, i) => (
                    <button
                      key={tab}
                      className={`px-4 py-2 text-[12px] font-medium border-b-2 transition-colors ${
                        i === 0
                          ? "text-gray-800 border-gray-800 bg-white"
                          : "text-gray-400 border-transparent hover:text-gray-600"
                      }`}
                    >
                      {tab}
                    </button>
                  ))}
                </div>

                {/* Code content */}
                <div className="bg-[#1e1e1e] p-5 overflow-x-auto">
                  <pre className="text-[13px] leading-[1.7] font-mono">
                    <code>
                      <span className="text-[#c586c0]">import</span>
                      <span className="text-[#d4d4d4]"> random</span>
                      {"\n\n"}
                      <span className="text-[#d4d4d4]">EMOJIS </span>
                      <span className="text-[#d4d4d4]">= </span>
                      <span className="text-[#d4d4d4]">{"{"}</span>
                      {"\n"}
                      <span className="text-[#d4d4d4]">    </span>
                      <span className="text-[#ce9178]">&quot;happy&quot;</span>
                      <span className="text-[#d4d4d4]">: </span>
                      <span className="text-[#ce9178]">&quot;{"\ud83d\ude0a"}&quot;</span>
                      <span className="text-[#d4d4d4]">,</span>
                      {"\n"}
                      <span className="text-[#d4d4d4]">    </span>
                      <span className="text-[#ce9178]">&quot;sad&quot;</span>
                      <span className="text-[#d4d4d4]">: </span>
                      <span className="text-[#ce9178]">&quot;{"\ud83d\ude22"}&quot;</span>
                      <span className="text-[#d4d4d4]">,</span>
                      {"\n"}
                      <span className="text-[#d4d4d4]">    </span>
                      <span className="text-[#ce9178]">&quot;excited&quot;</span>
                      <span className="text-[#d4d4d4]">: </span>
                      <span className="text-[#ce9178]">&quot;{"\ud83c\udf89"}&quot;</span>
                      <span className="text-[#d4d4d4]">,</span>
                      {"\n"}
                      <span className="text-[#d4d4d4]">    </span>
                      <span className="text-[#ce9178]">&quot;neutral&quot;</span>
                      <span className="text-[#d4d4d4]">: </span>
                      <span className="text-[#ce9178]">&quot;{"\ud83d\ude10"}&quot;</span>
                      {"\n"}
                      <span className="text-[#d4d4d4]">{"}"}</span>
                      {"\n\n"}
                      <span className="text-[#c586c0]">def</span>
                      <span className="text-[#dcdcaa]"> _choose_emoji</span>
                      <span className="text-[#d4d4d4]">(</span>
                      <span className="text-[#9cdcfe]">mood</span>
                      <span className="text-[#d4d4d4]">: </span>
                      <span className="text-[#4ec9b0]">str</span>
                      <span className="text-[#d4d4d4]">) -&gt; </span>
                      <span className="text-[#4ec9b0]">str</span>
                      <span className="text-[#d4d4d4]">:</span>
                      {"\n"}
                      <span className="text-[#d4d4d4]">    </span>
                      <span className="text-[#c586c0]">return</span>
                      <span className="text-[#d4d4d4]"> EMOJIS.</span>
                      <span className="text-[#dcdcaa]">get</span>
                      <span className="text-[#d4d4d4]">(mood.</span>
                      <span className="text-[#dcdcaa]">lower</span>
                      <span className="text-[#d4d4d4]">(), random.</span>
                      <span className="text-[#dcdcaa]">choice</span>
                      <span className="text-[#d4d4d4]">(</span>
                      <span className="text-[#4ec9b0]">list</span>
                      <span className="text-[#d4d4d4]">(EMOJIS.</span>
                      <span className="text-[#dcdcaa]">values</span>
                      <span className="text-[#d4d4d4]">())))</span>
                      {"\n\n"}
                      <span className="text-[#c586c0]">async</span>
                      <span className="text-[#c586c0]"> def</span>
                      <span className="text-[#dcdcaa]"> execute</span>
                      <span className="text-[#d4d4d4]">(</span>
                      <span className="text-[#9cdcfe]">inputs</span>
                      <span className="text-[#d4d4d4]">, </span>
                      <span className="text-[#9cdcfe]">config</span>
                      <span className="text-[#d4d4d4]">, </span>
                      <span className="text-[#9cdcfe]">context</span>
                      <span className="text-[#d4d4d4]">):</span>
                      {"\n"}
                      <span className="text-[#d4d4d4]">    </span>
                      <span className="text-[#6a9955]">&quot;&quot;&quot;Demo worker: builds a friendly greeting&quot;&quot;&quot;</span>
                    </code>
                  </pre>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── 6. Trust Bar ─────────────────────────── */}
      <section className="py-12 bg-white border-t border-gray-100">
        <div className="max-w-[900px] mx-auto px-6">
          <div className="flex flex-col sm:flex-row items-center justify-center gap-8 sm:gap-16">
            {[
              { number: "586", label: "agent runs" },
              { number: "94.4%", label: "success rate" },
              { number: "3 min", label: "v1 to production" },
            ].map((stat) => (
              <div key={stat.label} className="text-center">
                <span className="text-[28px] font-medium tracking-tight text-[#111827]">
                  {stat.number}
                </span>
                <span className="text-[14px] text-gray-400 ml-2">
                  {stat.label}
                </span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── 7. CTA ────────────────────────────────── */}
      <section className="py-32 px-6">
        <div className="bg-[#0a0a0a] rounded-[32px] max-w-4xl mx-auto p-12 md:p-20 text-center">
          <h2 className="text-[36px] md:text-[40px] text-white font-medium tracking-tight mb-4 leading-tight">
            Build your first agent
          </h2>
          <p className="text-[16px] text-white/50 max-w-md mx-auto mb-10 leading-relaxed">
            Open the visual builder, drag in your first nodes, and deploy a
            working agent in minutes&nbsp;&mdash; no boilerplate required.
          </p>
          <Link
            href="/admin/agents"
            className="inline-flex items-center gap-2 px-7 py-3.5 bg-white text-black hover:bg-gray-100 text-[14px] font-medium rounded-full transition-colors group"
          >
            Start building
            <ArrowRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
          </Link>
        </div>
      </section>

      {/* ── Footer ────────────────────────────────── */}
      <footer className="border-t border-gray-100 py-10 px-6">
        <div className="max-w-[1100px] mx-auto flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <div className="w-5 h-5 bg-[#111] text-white font-medium text-[11px] flex items-center justify-center rounded-[3px]">
              T
            </div>
            <span className="text-[13px] text-gray-400">
              Talmudpedia
            </span>
          </div>
          <div className="flex items-center gap-6 text-[13px] text-gray-400">
            <Link href="#" className="hover:text-gray-600 transition-colors">
              Docs
            </Link>
            <Link href="#" className="hover:text-gray-600 transition-colors">
              Platform
            </Link>
            <Link
              href="/auth/login"
              className="hover:text-gray-600 transition-colors"
            >
              Sign in
            </Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
