"use client";

import { useEffect, useState, useRef } from "react";
import Link from "next/link";

/* ───────────────────────────────────────────
   V2 — OBSIDIAN
   Inspired directly by obsidianos.com
   Near-black with warm undertone, ultra-light
   weight serif, glassmorphic nav, blurred orbs,
   flowing sections (no cards), pure type hierarchy,
   zero decorative icons.
   ─────────────────────────────────────────── */

function useReveal(threshold = 0.15) {
  const ref = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      ([e]) => { if (e.isIntersecting) { setVisible(true); obs.disconnect(); } },
      { threshold }
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, [threshold]);
  return { ref, visible };
}

function Section({
  children,
  className = "",
  delay = 0,
}: {
  children: React.ReactNode;
  className?: string;
  delay?: number;
}) {
  const { ref, visible } = useReveal();
  return (
    <div
      ref={ref}
      style={{ transitionDelay: `${delay}ms` }}
      className={`transition-all duration-[1200ms] ease-[cubic-bezier(0.16,1,0.3,1)] ${
        visible ? "translate-y-0 opacity-100" : "translate-y-8 opacity-0"
      } ${className}`}
    >
      {children}
    </div>
  );
}

export function LandingV2() {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  return (
    <div className="relative min-h-screen bg-[#050505] text-white selection:bg-white/20">
      <style>{`@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,300;0,400;1,300;1,400&display=swap');`}</style>

      {/* Ambient orbs */}
      <div className="pointer-events-none fixed inset-0 overflow-hidden">
        <div className="absolute -top-[300px] left-1/2 h-[800px] w-[1000px] -translate-x-1/2 rounded-full bg-gradient-to-b from-[#1a1815]/40 to-transparent blur-[150px]" />
        <div className="absolute bottom-[-200px] right-[-100px] h-[500px] w-[600px] rounded-full bg-[#0f0e0b]/50 blur-[120px]" />
        <div className="absolute top-[50%] left-[-200px] h-[400px] w-[400px] rounded-full bg-[#131210]/30 blur-[100px]" />
      </div>

      {/* Nav — glassmorphic */}
      <nav
        className={`fixed top-0 z-50 w-full transition-all duration-700 ${
          mounted ? "translate-y-0 opacity-100" : "-translate-y-4 opacity-0"
        }`}
      >
        <div className="mx-auto max-w-[1280px] px-8 py-5">
          <div className="flex items-center justify-between rounded-2xl border border-white/[0.04] bg-white/[0.02] px-6 py-3 backdrop-blur-[24px]">
            <Link href="/" className="text-[14px] text-white/60">
              Talmudpedia
            </Link>
            <div className="hidden items-center gap-8 md:flex">
              {["Platform", "Agents", "Docs"].map((item) => (
                <span
                  key={item}
                  className="cursor-pointer text-[13px] text-white/25 transition-colors duration-300 hover:text-white/50"
                >
                  {item}
                </span>
              ))}
            </div>
            <Link
              href="/auth/login"
              className="rounded-full border border-white/[0.08] bg-white/[0.04] px-5 py-2 text-[13px] text-white/50 backdrop-blur-sm transition-all duration-300 hover:border-white/[0.12] hover:bg-white/[0.06] hover:text-white/70"
            >
              Sign in
            </Link>
          </div>
        </div>
      </nav>

      {/* Hero — massive serif */}
      <section className="relative px-8 pt-48 pb-48 md:pt-56 md:pb-56">
        <div
          className={`mx-auto max-w-[1280px] text-center transition-all duration-[1400ms] ease-[cubic-bezier(0.16,1,0.3,1)] ${
            mounted ? "translate-y-0 opacity-100" : "translate-y-16 opacity-0"
          }`}
        >
          <h1
            className="mx-auto max-w-[900px] text-[clamp(3rem,8vw,7rem)] leading-[0.95] tracking-[-0.03em]"
            style={{ fontFamily: "'Cormorant Garamond', Georgia, serif", fontWeight: 300 }}
          >
            Build AI that
            <br />
            <em className="text-white/40">thinks in graphs</em>
          </h1>

          <p className="mx-auto mt-10 max-w-[420px] text-[14px] leading-[1.8] text-white/20">
            The multi-tenant platform for agent authoring, knowledge pipelines,
            and deployed AI applications.
          </p>

          <div className="mt-12 flex items-center justify-center gap-6">
            <Link
              href="/auth/login"
              className="rounded-full border border-white/[0.08] bg-white/[0.04] px-7 py-3 text-[13px] text-white/60 backdrop-blur-sm transition-all duration-300 hover:border-white/[0.15] hover:bg-white/[0.08] hover:text-white/80"
            >
              Get started
            </Link>
            <Link
              href="/admin/apps"
              className="text-[13px] text-white/20 underline decoration-white/[0.06] underline-offset-4 transition-colors duration-300 hover:text-white/35 hover:decoration-white/15"
            >
              Explore platform
            </Link>
          </div>
        </div>
      </section>

      {/* Statement — flowing text, no cards */}
      <section className="px-8 pb-48">
        <Section>
          <div className="mx-auto max-w-[1280px]">
            <div className="mx-auto max-w-[720px]">
              <p
                className="text-[clamp(1.4rem,3vw,2.2rem)] leading-[1.4] tracking-[-0.015em] text-white/50"
                style={{ fontFamily: "'Cormorant Garamond', Georgia, serif", fontWeight: 300 }}
              >
                Talmudpedia is not another wrapper around a language model. It is a
                platform where{" "}
                <span className="text-white/90">agents reason through directed graphs</span>,
                where{" "}
                <span className="text-white/90">RAG pipelines compile raw data into knowledge</span>,
                and where{" "}
                <span className="text-white/90">applications ship to real users</span> — all
                under one governance layer with full tracing and tenant isolation.
              </p>
            </div>
          </div>
        </Section>
      </section>

      {/* Capabilities — flowing, no grids */}
      <section className="px-8 pb-48">
        <div className="mx-auto max-w-[1280px]">
          {[
            {
              n: "01",
              title: "Agent graphs",
              body: "Reasoning flows designed as composable directed graphs. Every node is typed — logic, tools, retrieval, orchestration — every edge validated. Execution traces persist for debugging and audit.",
            },
            {
              n: "02",
              title: "Knowledge pipelines",
              body: "Graph-based RAG operators handle the full journey from raw document to retrievable knowledge. Chunking, embedding, crawling, vector storage, and semantic retrieval — all through a visual operator registry.",
            },
            {
              n: "03",
              title: "Edge artifacts",
              body: "Custom runtime code deployed as platform artifacts. Tools, agent nodes, and RAG operators execute on Cloudflare Workers. Version-controlled, diff-supported, with an integrated coding assistant.",
            },
            {
              n: "04",
              title: "Shipped applications",
              body: "Complete AI-powered apps deployed to end users. PRICO widget layouts, embedded agent runtimes, custom domains, interactive surfaces. From builder to production in one workflow.",
            },
            {
              n: "05",
              title: "Governance",
              body: "Multi-tenant isolation as a first-class concern, not an afterthought. Full audit trails, execution tracing, model routing policies, and role-based access control across every surface.",
            },
          ].map((item, i) => (
            <Section key={item.n} delay={i * 60}>
              <div className="border-t border-white/[0.04] py-16 md:py-20">
                <div className="grid grid-cols-1 gap-6 md:grid-cols-[100px_280px_1fr] md:gap-10">
                  <span className="font-mono text-[11px] text-white/10">{item.n}</span>
                  <h3
                    className="text-[clamp(1.2rem,2vw,1.6rem)] tracking-[-0.02em] text-white/70"
                    style={{ fontFamily: "'Cormorant Garamond', Georgia, serif", fontWeight: 400 }}
                  >
                    {item.title}
                  </h3>
                  <p className="max-w-[500px] text-[13px] leading-[1.9] text-white/20">
                    {item.body}
                  </p>
                </div>
              </div>
            </Section>
          ))}
        </div>
      </section>

      {/* Architecture — stacked layers */}
      <section className="px-8 pb-48">
        <Section>
          <div className="mx-auto max-w-[720px] text-center">
            <p className="mb-4 font-mono text-[10px] uppercase tracking-[0.4em] text-white/10">
              Architecture
            </p>
            <h2
              className="text-[clamp(1.6rem,3.5vw,2.6rem)] leading-[1.15] tracking-[-0.02em] text-white/70"
              style={{ fontFamily: "'Cormorant Garamond', Georgia, serif", fontWeight: 300 }}
            >
              Five layers, clear boundaries
            </h2>
            <p className="mx-auto mt-5 max-w-[380px] text-[13px] leading-[1.8] text-white/15">
              Each layer owns one concern. Each contract is explicit.
              From identity at the base to applications at the surface.
            </p>
          </div>
        </Section>

        <div className="mx-auto mt-20 max-w-[600px]">
          {[
            { name: "Applications", o: "90" },
            { name: "Agent Execution", o: "65" },
            { name: "RAG & Knowledge", o: "45" },
            { name: "Shared Resources", o: "28" },
            { name: "Foundation", o: "15" },
          ].map((l, i) => (
            <Section key={l.name} delay={i * 100}>
              <div
                className="border-b border-white/[0.03] py-5"
                style={{ paddingLeft: `${i * 24}px` }}
              >
                <span
                  className="text-[15px] tracking-[-0.01em]"
                  style={{ opacity: Number(l.o) / 100 }}
                >
                  {l.name}
                </span>
              </div>
            </Section>
          ))}
        </div>
      </section>

      {/* CTA */}
      <section className="px-8 pb-48">
        <Section>
          <div className="mx-auto max-w-[1280px] text-center">
            <h2
              className="text-[clamp(2rem,5vw,3.8rem)] leading-[1.05] tracking-[-0.03em] text-white/80"
              style={{ fontFamily: "'Cormorant Garamond', Georgia, serif", fontWeight: 300 }}
            >
              Begin
            </h2>
            <div className="mt-10">
              <Link
                href="/auth/login"
                className="rounded-full border border-white/[0.08] bg-white/[0.04] px-8 py-3.5 text-[13px] text-white/50 backdrop-blur-sm transition-all duration-300 hover:border-white/[0.15] hover:bg-white/[0.08] hover:text-white/70"
              >
                Create account
              </Link>
            </div>
          </div>
        </Section>
      </section>

      {/* Footer */}
      <footer className="border-t border-white/[0.03] px-8 py-10">
        <div className="mx-auto flex max-w-[1280px] items-center justify-between">
          <span className="text-[12px] text-white/10">© 2026 Talmudpedia</span>
          <span className="text-[12px] text-white/10">Multi-tenant AI platform</span>
        </div>
      </footer>
    </div>
  );
}
