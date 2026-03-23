"use client";

import { useEffect, useState, useRef } from "react";
import Link from "next/link";
import {
  ArrowRight,
  Terminal,
  ChevronRight,
} from "lucide-react";

/* ───────────────────────────────────────────
   V4 — TERMINAL / HACKER
   Code-like typography, terminal-style sections,
   phosphor green on dark, typing animations,
   CRT scanline texture, monospace everything
   ─────────────────────────────────────────── */

function TypeWriter({ text, speed = 40 }: { text: string; speed?: number }) {
  const [displayed, setDisplayed] = useState("");
  const [showCursor, setShowCursor] = useState(true);
  const started = useRef(false);
  const ref = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting && !started.current) {
          started.current = true;
          let i = 0;
          const interval = setInterval(() => {
            if (i < text.length) {
              setDisplayed(text.slice(0, i + 1));
              i++;
            } else {
              clearInterval(interval);
              setTimeout(() => setShowCursor(false), 2000);
            }
          }, speed);
        }
      },
      { threshold: 0.5 }
    );
    if (ref.current) observer.observe(ref.current);
    return () => observer.disconnect();
  }, [text, speed]);

  return (
    <span ref={ref}>
      {displayed}
      {showCursor && (
        <span className="animate-pulse text-[#39ff14]">▋</span>
      )}
    </span>
  );
}

function TerminalBlock({
  prompt,
  output,
  delay = "0ms",
}: {
  prompt: string;
  output: string[];
  delay?: string;
}) {
  const [visible, setVisible] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const observer = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting) setVisible(true); },
      { threshold: 0.2 }
    );
    if (ref.current) observer.observe(ref.current);
    return () => observer.disconnect();
  }, []);

  return (
    <div
      ref={ref}
      style={{ transitionDelay: delay }}
      className={`rounded-lg border border-[#39ff14]/10 bg-[#0a0f0a] p-5 font-mono transition-all duration-700 ${
        visible ? "translate-y-0 opacity-100" : "translate-y-6 opacity-0"
      }`}
    >
      <div className="mb-3 flex items-center gap-2 text-xs text-[#39ff14]/40">
        <Terminal className="h-3 w-3" />
        <span>talmudpedia</span>
      </div>
      <div className="text-sm">
        <div className="flex gap-2">
          <span className="text-[#39ff14]/60">$</span>
          <span className="text-[#39ff14]">{prompt}</span>
        </div>
        <div className="mt-2 space-y-1">
          {output.map((line, i) => (
            <div key={i} className="text-[#39ff14]/40">
              {line}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export function LandingV4() {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  return (
    <div className="relative min-h-screen bg-[#0a0f0a] font-mono text-[#39ff14] selection:bg-[#39ff14] selection:text-[#0a0f0a]">
      {/* CRT scanline overlay */}
      <div
        className="pointer-events-none fixed inset-0 z-[60] opacity-[0.03]"
        style={{
          backgroundImage:
            "repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0,0,0,0.3) 2px, rgba(0,0,0,0.3) 4px)",
        }}
      />

      {/* Ambient glow */}
      <div className="pointer-events-none fixed inset-0 overflow-hidden">
        <div className="absolute left-1/2 top-0 h-[400px] w-[600px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-[#39ff14]/[0.02] blur-[120px]" />
      </div>

      {/* Nav */}
      <nav
        className={`fixed top-0 z-50 w-full transition-all duration-700 ${
          mounted ? "translate-y-0 opacity-100" : "-translate-y-4 opacity-0"
        }`}
      >
        <div className="mx-auto flex max-w-6xl items-center justify-between border-b border-[#39ff14]/[0.06] px-6 py-4">
          <div className="flex items-center gap-2">
            <span className="text-[#39ff14]/60">~/</span>
            <span className="text-xs text-[#39ff14]/80">talmudpedia</span>
          </div>
          <div className="hidden items-center gap-6 md:flex">
            {["--platform", "--agents", "--rag", "--docs"].map((cmd) => (
              <span
                key={cmd}
                className="cursor-pointer text-[11px] text-[#39ff14]/30 transition-colors hover:text-[#39ff14]/70"
              >
                {cmd}
              </span>
            ))}
          </div>
          <Link
            href="/auth/login"
            className="border border-[#39ff14]/20 px-4 py-1.5 text-[11px] text-[#39ff14]/60 transition-all duration-300 hover:border-[#39ff14]/40 hover:bg-[#39ff14]/5 hover:text-[#39ff14]"
          >
            $ login
          </Link>
        </div>
      </nav>

      {/* Hero */}
      <section className="relative flex min-h-screen flex-col items-center justify-center px-6 pt-20">
        <div
          className={`mx-auto max-w-4xl transition-all duration-1000 delay-200 ${
            mounted ? "translate-y-0 opacity-100" : "translate-y-8 opacity-0"
          }`}
        >
          <div className="mb-8 flex items-center gap-2 text-xs text-[#39ff14]/30">
            <ChevronRight className="h-3 w-3" />
            <span>system.boot</span>
            <span className="ml-2 text-[#39ff14]/50">v2.0.0-beta</span>
          </div>

          <h1 className="text-4xl font-normal leading-[1.2] tracking-[-0.02em] md:text-6xl lg:text-7xl">
            <span className="text-[#39ff14]/90">
              <TypeWriter text="Multi-tenant AI infrastructure" speed={35} />
            </span>
          </h1>

          <div className="mt-8 max-w-2xl border-l-2 border-[#39ff14]/20 pl-4">
            <p className="text-sm leading-relaxed text-[#39ff14]/35">
              Graph-based agent authoring. RAG pipeline compilation. Artifact
              execution at the edge. Published app runtimes. Full governance
              and tracing. One platform, zero compromises.
            </p>
          </div>

          <div className="mt-12 flex flex-col gap-3 sm:flex-row">
            <Link
              href="/auth/login"
              className="group flex items-center gap-2 border border-[#39ff14] bg-[#39ff14] px-6 py-3 text-sm font-medium text-[#0a0f0a] transition-all duration-300 hover:bg-[#39ff14]/90"
            >
              <span>$ init --start</span>
              <ArrowRight className="h-4 w-4 transition-transform duration-300 group-hover:translate-x-1" />
            </Link>
            <Link
              href="/admin/apps"
              className="flex items-center gap-2 border border-[#39ff14]/20 px-6 py-3 text-sm text-[#39ff14]/60 transition-all duration-300 hover:border-[#39ff14]/40 hover:text-[#39ff14]"
            >
              $ explore --demo
            </Link>
          </div>
        </div>
      </section>

      {/* System Overview */}
      <section className="px-6 pb-32">
        <div className="mx-auto max-w-5xl">
          <div className="mb-12 flex items-center gap-2 text-xs text-[#39ff14]/30">
            <ChevronRight className="h-3 w-3" />
            <span>platform.describe --modules</span>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <TerminalBlock
              prompt="tp agent --info"
              output={[
                "Agent Graph Engine v2.0",
                "├── Visual graph authoring",
                "├── Node types: logic, tool, retrieval, orchestration",
                "├── Compiled execution via runtime adapters",
                "├── Threaded runs with persisted traces",
                "└── Heterogeneous node execution support",
              ]}
              delay="0ms"
            />
            <TerminalBlock
              prompt="tp rag --info"
              output={[
                "RAG Pipeline Engine v2.0",
                "├── Graph-based operator registry",
                "├── Ingestion: chunk, embed, crawl, store",
                "├── Retrieval: semantic search, hybrid",
                "├── Knowledge store abstraction",
                "└── Vector backend providers",
              ]}
              delay="100ms"
            />
            <TerminalBlock
              prompt="tp artifact --info"
              output={[
                "Artifact Runtime v2.0",
                "├── Custom code as platform extensions",
                "├── Edge execution via CF Workers",
                "├── Types: tool, agent-node, rag-operator",
                "├── Version control + diff support",
                "└── AI coding assistant integration",
              ]}
              delay="200ms"
            />
            <TerminalBlock
              prompt="tp apps --info"
              output={[
                "Published Apps Runtime v2.0",
                "├── PRICO widget layout system",
                "├── Embedded agent runtimes",
                "├── Custom branding + domains",
                "├── Interactive widget surfaces",
                "└── End-user facing deployments",
              ]}
              delay="300ms"
            />
          </div>
        </div>
      </section>

      {/* Architecture as code */}
      <section className="px-6 pb-32">
        <div className="mx-auto max-w-5xl">
          <div className="rounded-lg border border-[#39ff14]/10 bg-[#0a0f0a] p-8">
            <div className="mb-6 flex items-center gap-2 text-xs text-[#39ff14]/40">
              <Terminal className="h-3 w-3" />
              <span>architecture.yaml</span>
            </div>
            <pre className="text-sm leading-7 text-[#39ff14]/50">
{`platform:
  name: talmudpedia
  type: multi-tenant-ai-platform

  layers:
    - name: foundation          # Layer 0
      owns: [tenancy, auth, identity, policy]

    - name: shared_resources    # Layer 1
      owns: [models, tools, artifacts, providers]

    - name: rag                 # Layer 2
      owns: [pipelines, knowledge_stores, retrieval]

    - name: agents              # Layer 3
      owns: [graphs, execution, traces, reasoning]

    - name: applications        # Layer 4
      owns: [published_apps, widgets, runtimes]

  guarantees:
    tenant_isolation: `}<span className="text-[#39ff14]">strict</span>{`
    execution_tracing: `}<span className="text-[#39ff14]">full</span>{`
    governance: `}<span className="text-[#39ff14]">built_in</span></pre>
          </div>
        </div>
      </section>

      {/* Stats */}
      <section className="px-6 pb-32">
        <div className="mx-auto max-w-5xl">
          <div className="grid gap-4 md:grid-cols-4">
            {[
              { cmd: "latency --p95", val: "<200ms" },
              { cmd: "layers --count", val: "5" },
              { cmd: "isolation --mode", val: "strict" },
              { cmd: "edge --provider", val: "cf-workers" },
            ].map((s) => (
              <div
                key={s.cmd}
                className="border border-[#39ff14]/[0.06] bg-[#39ff14]/[0.02] p-5"
              >
                <div className="mb-2 text-[10px] text-[#39ff14]/30">
                  $ tp {s.cmd}
                </div>
                <div className="text-2xl text-[#39ff14]/80">{s.val}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="px-6 pb-40">
        <div className="mx-auto max-w-2xl text-center">
          <div className="mb-6 text-xs text-[#39ff14]/30">
            ready to deploy? initialize your tenant.
          </div>
          <div className="mb-8 text-3xl text-[#39ff14]/80 md:text-4xl">
            $ tp init --tenant your-org
          </div>
          <Link
            href="/auth/login"
            className="group inline-flex items-center gap-2 border border-[#39ff14] bg-[#39ff14] px-8 py-4 text-sm font-medium text-[#0a0f0a] transition-all duration-300 hover:shadow-[0_0_30px_rgba(57,255,20,0.15)]"
          >
            Initialize now
            <ArrowRight className="h-4 w-4 transition-transform duration-300 group-hover:translate-x-1" />
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-[#39ff14]/[0.06] px-6 py-6">
        <div className="mx-auto flex max-w-5xl items-center justify-between text-[10px] text-[#39ff14]/20">
          <span>© 2026 talmudpedia</span>
          <span>PID 1 · uptime 99.99%</span>
        </div>
      </footer>
    </div>
  );
}
