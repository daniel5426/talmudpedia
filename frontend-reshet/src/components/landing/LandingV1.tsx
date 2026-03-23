"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import Link from "next/link";
import { ArrowRight } from "lucide-react";

/* ───────────────────────────────────────────
   V1 — NOIR
   Dark cinematic. Inspired by Origin Finance.
   Black canvas, serif display type, product
   screenshots as hero, scroll-triggered reveals,
   opacity-based hierarchy, zero icon grids.
   ─────────────────────────────────────────── */

function useScrollReveal() {
  const ref = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      ([e]) => { if (e.isIntersecting) { setVisible(true); obs.disconnect(); } },
      { threshold: 0.15 }
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, []);
  return { ref, visible };
}

function Reveal({
  children,
  className = "",
  delay = 0,
}: {
  children: React.ReactNode;
  className?: string;
  delay?: number;
}) {
  const { ref, visible } = useScrollReveal();
  return (
    <div
      ref={ref}
      style={{ transitionDelay: `${delay}ms` }}
      className={`transition-all duration-[1000ms] ease-[cubic-bezier(0.16,1,0.3,1)] ${
        visible ? "translate-y-0 opacity-100" : "translate-y-10 opacity-0"
      } ${className}`}
    >
      {children}
    </div>
  );
}

function ProductMockup() {
  return (
    <div className="relative mx-auto w-full max-w-[1100px]">
      {/* Browser chrome */}
      <div className="overflow-hidden rounded-2xl border border-white/[0.06] bg-[#111] shadow-[0_60px_140px_rgba(0,0,0,0.7)]">
        {/* Title bar */}
        <div className="flex items-center gap-2 border-b border-white/[0.04] px-5 py-3.5">
          <div className="flex gap-1.5">
            <div className="h-2.5 w-2.5 rounded-full bg-white/10" />
            <div className="h-2.5 w-2.5 rounded-full bg-white/10" />
            <div className="h-2.5 w-2.5 rounded-full bg-white/10" />
          </div>
          <div className="ml-3 h-5 w-64 rounded-md bg-white/[0.04]" />
        </div>
        {/* App content */}
        <div className="grid grid-cols-[220px_1fr] min-h-[420px]">
          {/* Sidebar */}
          <div className="border-r border-white/[0.04] bg-[#0c0c0c] px-3 py-4">
            <div className="mb-6 px-2">
              <div className="h-3 w-16 rounded bg-white/10" />
            </div>
            <div className="space-y-0.5">
              {["Agents", "RAG Pipelines", "Knowledge", "Models", "Tools", "Artifacts", "Apps"].map(
                (item, i) => (
                  <div
                    key={item}
                    className={`rounded-lg px-3 py-2 text-[12px] tracking-wide ${
                      i === 0
                        ? "bg-white/[0.06] text-white/70"
                        : "text-white/25"
                    }`}
                  >
                    {item}
                  </div>
                )
              )}
            </div>
          </div>
          {/* Main */}
          <div className="p-6">
            <div className="mb-6 flex items-center justify-between">
              <div className="h-4 w-28 rounded bg-white/8" />
              <div className="h-7 w-20 rounded-lg bg-white/10" />
            </div>
            {/* Agent graph mock */}
            <div className="relative rounded-xl border border-white/[0.04] bg-[#0a0a0a] p-8">
              <div className="flex items-center justify-between gap-6">
                {[
                  { w: "w-24", h: "h-16", label: "Input" },
                  { w: "w-28", h: "h-20", label: "Reason" },
                  { w: "w-24", h: "h-16", label: "Retrieve" },
                  { w: "w-28", h: "h-20", label: "Decide" },
                  { w: "w-24", h: "h-16", label: "Output" },
                ].map((node, i) => (
                  <div key={node.label} className="flex flex-col items-center gap-2">
                    <div
                      className={`${node.w} ${node.h} rounded-xl border border-white/[0.06] bg-white/[0.03] flex items-center justify-center`}
                    >
                      <span className="text-[10px] text-white/20">{node.label}</span>
                    </div>
                    {i < 4 && <div className="hidden" />}
                  </div>
                ))}
              </div>
              {/* Connection line */}
              <div className="absolute top-1/2 left-[12%] right-[12%] h-[1px] -translate-y-1/2 bg-gradient-to-r from-white/0 via-white/[0.06] to-white/0" />
            </div>
            {/* Bottom stats */}
            <div className="mt-6 grid grid-cols-3 gap-3">
              {[
                { label: "Active agents", val: "12" },
                { label: "Executions today", val: "1,847" },
                { label: "Avg latency", val: "142ms" },
              ].map((s) => (
                <div key={s.label} className="rounded-lg border border-white/[0.03] bg-white/[0.02] px-4 py-3">
                  <div className="text-[10px] text-white/20">{s.label}</div>
                  <div className="mt-1 text-sm text-white/50">{s.val}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export function LandingV1() {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  return (
    <div className="relative min-h-screen bg-black text-white selection:bg-white selection:text-black">
      <style>{`@import url('https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&display=swap');`}</style>

      {/* Nav */}
      <nav
        className={`fixed top-0 z-50 w-full transition-all duration-700 ${
          mounted ? "translate-y-0 opacity-100" : "-translate-y-4 opacity-0"
        }`}
      >
        <div className="mx-auto flex max-w-[1400px] items-center justify-between px-8 py-6">
          <Link href="/" className="text-[15px] font-medium tracking-[-0.02em] text-white/90">
            Talmudpedia
          </Link>
          <div className="hidden items-center gap-10 md:flex">
            {["Platform", "Agents", "RAG", "Docs"].map((item) => (
              <span
                key={item}
                className="cursor-pointer text-[13px] text-white/35 transition-colors duration-300 hover:text-white/70"
              >
                {item}
              </span>
            ))}
          </div>
          <Link
            href="/auth/login"
            className="rounded-full bg-white px-5 py-2 text-[13px] font-medium text-black transition-all duration-300 hover:bg-white/90"
          >
            Get started
          </Link>
        </div>
      </nav>

      {/* Hero */}
      <section className="relative px-8 pt-40 pb-32 md:pt-52 md:pb-40">
        <div
          className={`mx-auto max-w-[1400px] transition-all duration-[1200ms] ease-[cubic-bezier(0.16,1,0.3,1)] ${
            mounted ? "translate-y-0 opacity-100" : "translate-y-12 opacity-0"
          }`}
        >
          <h1
            className="max-w-[900px] text-[clamp(2.8rem,6.5vw,5.5rem)] leading-[1.05] tracking-[-0.035em] text-white/95"
            style={{ fontFamily: "'Instrument Serif', Georgia, serif" }}
          >
            The infrastructure for{" "}
            <em className="text-white/50">intelligent systems</em>
          </h1>

          <p className="mt-8 max-w-[520px] text-[15px] leading-[1.7] text-white/30">
            Build agents as graphs. Compose RAG pipelines. Ship AI-powered
            applications. Governed, traced, and multi-tenant from day one.
          </p>

          <div className="mt-10 flex items-center gap-5">
            <Link
              href="/auth/login"
              className="group flex items-center gap-2.5 rounded-full bg-white px-7 py-3.5 text-[13px] font-medium text-black transition-all duration-300 hover:bg-white/90"
            >
              Start building
              <ArrowRight className="h-3.5 w-3.5 transition-transform duration-300 group-hover:translate-x-0.5" strokeWidth={2} />
            </Link>
            <Link
              href="/admin/apps"
              className="text-[13px] text-white/30 underline decoration-white/10 underline-offset-4 transition-colors duration-300 hover:text-white/50 hover:decoration-white/25"
            >
              View live demo
            </Link>
          </div>
        </div>
      </section>

      {/* Product screenshot */}
      <section className="px-8 pb-40">
        <Reveal>
          <ProductMockup />
        </Reveal>
      </section>

      {/* Statement */}
      <section className="px-8 pb-40">
        <Reveal>
          <div className="mx-auto max-w-[1400px]">
            <h2
              className="max-w-[800px] text-[clamp(1.8rem,4vw,3.2rem)] leading-[1.2] tracking-[-0.03em] text-white/90"
              style={{ fontFamily: "'Instrument Serif', Georgia, serif" }}
            >
              Not another chatbot wrapper.{" "}
              <span className="text-white/30">
                A platform where agents reason through graphs, RAG pipelines
                compile knowledge, and applications ship to real users — all
                under one governance layer.
              </span>
            </h2>
          </div>
        </Reveal>
      </section>

      {/* Capabilities — no icons, just type */}
      <section className="px-8 pb-40">
        <div className="mx-auto max-w-[1400px]">
          <Reveal>
            <p className="mb-20 text-[11px] uppercase tracking-[0.3em] text-white/20">
              What you get
            </p>
          </Reveal>

          <div className="space-y-0">
            {[
              {
                title: "Agent graph authoring",
                desc: "Design reasoning flows as directed graphs. Logic, tools, retrieval, and orchestration compose into executable architectures with typed nodes and validated edges.",
              },
              {
                title: "RAG pipeline builder",
                desc: "From raw documents to retrievable knowledge. Graph-based operators handle chunking, embedding, crawling, and vector storage with knowledge store abstraction.",
              },
              {
                title: "Artifact extensions",
                desc: "Deploy custom runtime code as platform artifacts. Tools, agent nodes, and RAG operators execute at the edge via Cloudflare Workers with near-zero cold start.",
              },
              {
                title: "Published applications",
                desc: "Ship complete AI apps with PRICO widget layouts, embedded agent runtimes, custom branding, and interactive surfaces — directly to end users.",
              },
              {
                title: "Multi-tenant governance",
                desc: "Tenant isolation, full audit trails, execution tracing, model routing policies, and RBAC. Enterprise-grade controls without enterprise-grade complexity.",
              },
            ].map((item, i) => (
              <Reveal key={item.title} delay={i * 80}>
                <div className="group grid grid-cols-1 gap-4 border-t border-white/[0.05] py-10 md:grid-cols-[1fr_1.2fr] md:gap-20">
                  <h3
                    className="text-[clamp(1.3rem,2.5vw,1.8rem)] leading-[1.2] tracking-[-0.02em] text-white/80 transition-colors duration-500 group-hover:text-white"
                    style={{ fontFamily: "'Instrument Serif', Georgia, serif" }}
                  >
                    {item.title}
                  </h3>
                  <p className="text-[14px] leading-[1.8] text-white/25 transition-colors duration-500 group-hover:text-white/40">
                    {item.desc}
                  </p>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* Architecture — minimal */}
      <section className="px-8 pb-40">
        <div className="mx-auto max-w-[1400px]">
          <div className="grid gap-20 md:grid-cols-2">
            <Reveal>
              <div>
                <p className="mb-6 text-[11px] uppercase tracking-[0.3em] text-white/20">
                  Architecture
                </p>
                <h2
                  className="text-[clamp(1.8rem,3.5vw,2.8rem)] leading-[1.15] tracking-[-0.03em] text-white/90"
                  style={{ fontFamily: "'Instrument Serif', Georgia, serif" }}
                >
                  Five layers,
                  <br />
                  zero ambiguity
                </h2>
                <p className="mt-6 max-w-[400px] text-[14px] leading-[1.8] text-white/25">
                  Every layer owns a single concern with clear contracts to its
                  neighbors. Foundation handles tenancy. Resources manage models.
                  RAG builds knowledge. Agents reason. Apps deliver.
                </p>
              </div>
            </Reveal>

            <Reveal delay={200}>
              <div className="space-y-2 pt-4">
                {[
                  { n: "04", name: "Applications", opacity: "text-white/80 border-white/[0.08]" },
                  { n: "03", name: "Agent Execution", opacity: "text-white/60 border-white/[0.06]" },
                  { n: "02", name: "RAG & Knowledge", opacity: "text-white/40 border-white/[0.05]" },
                  { n: "01", name: "Shared Resources", opacity: "text-white/25 border-white/[0.04]" },
                  { n: "00", name: "Platform Foundation", opacity: "text-white/15 border-white/[0.03]" },
                ].map((layer) => (
                  <div
                    key={layer.n}
                    className={`flex items-center justify-between border-b px-1 py-4 ${layer.opacity}`}
                  >
                    <span className="text-[14px] tracking-[-0.01em]">{layer.name}</span>
                    <span className="font-mono text-[11px] opacity-50">{layer.n}</span>
                  </div>
                ))}
              </div>
            </Reveal>
          </div>
        </div>
      </section>

      {/* Numbers */}
      <section className="px-8 pb-40">
        <div className="mx-auto max-w-[1400px]">
          <Reveal>
            <div className="grid grid-cols-1 gap-16 border-t border-white/[0.05] pt-16 md:grid-cols-3">
              {[
                { val: "<200ms", label: "Agent cold-start latency at p95" },
                { val: "100%", label: "Tenant isolation — zero data cross-leak" },
                { val: "Edge", label: "Artifact execution on Cloudflare Workers" },
              ].map((stat) => (
                <div key={stat.label}>
                  <div
                    className="text-[clamp(2rem,4vw,3.5rem)] tracking-[-0.03em] text-white/90"
                    style={{ fontFamily: "'Instrument Serif', Georgia, serif" }}
                  >
                    {stat.val}
                  </div>
                  <p className="mt-2 text-[13px] leading-[1.6] text-white/20">
                    {stat.label}
                  </p>
                </div>
              ))}
            </div>
          </Reveal>
        </div>
      </section>

      {/* CTA */}
      <section className="px-8 pb-40">
        <Reveal>
          <div className="mx-auto max-w-[1400px] text-center">
            <h2
              className="text-[clamp(2rem,5vw,4rem)] leading-[1.1] tracking-[-0.03em] text-white/90"
              style={{ fontFamily: "'Instrument Serif', Georgia, serif" }}
            >
              Start building today
            </h2>
            <p className="mx-auto mt-5 max-w-[400px] text-[14px] leading-[1.7] text-white/25">
              From prototype to production. The platform for teams who ship
              intelligent systems at scale.
            </p>
            <div className="mt-10">
              <Link
                href="/auth/login"
                className="group inline-flex items-center gap-2.5 rounded-full bg-white px-8 py-4 text-[14px] font-medium text-black transition-all duration-300 hover:bg-white/90"
              >
                Create free account
                <ArrowRight className="h-4 w-4 transition-transform duration-300 group-hover:translate-x-0.5" strokeWidth={2} />
              </Link>
            </div>
          </div>
        </Reveal>
      </section>

      {/* Footer */}
      <footer className="border-t border-white/[0.04] px-8 py-10">
        <div className="mx-auto flex max-w-[1400px] items-center justify-between">
          <span className="text-[13px] text-white/20">© 2026 Talmudpedia</span>
          <div className="flex gap-8">
            {["Platform", "Docs", "GitHub"].map((l) => (
              <span key={l} className="cursor-pointer text-[13px] text-white/15 transition-colors duration-300 hover:text-white/30">
                {l}
              </span>
            ))}
          </div>
        </div>
      </footer>
    </div>
  );
}
