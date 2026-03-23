"use client";

import { useEffect, useState, useRef } from "react";
import Link from "next/link";
import {
  ArrowRight,
  Workflow,
  Database,
  Blocks,
  Shield,
  Cpu,
  Layers,
  Sparkles,
  Zap,
} from "lucide-react";

/* ───────────────────────────────────────────
   V3 — GRADIENT MESH
   Vibrant gradients, floating cards,
   bold modern SaaS feel, saturated accents,
   mesh background, energetic motion
   ─────────────────────────────────────────── */

function FloatingCard({
  icon: Icon,
  title,
  description,
  gradient,
  delay,
}: {
  icon: React.ElementType;
  title: string;
  description: string;
  gradient: string;
  delay: string;
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
      className={`group relative overflow-hidden rounded-3xl border border-white/20 bg-white/80 p-7 shadow-xl backdrop-blur-xl transition-all duration-700 hover:-translate-y-1 hover:shadow-2xl ${
        visible ? "translate-y-0 opacity-100" : "translate-y-8 opacity-0"
      }`}
    >
      <div
        className={`absolute inset-0 opacity-0 transition-opacity duration-500 group-hover:opacity-100 ${gradient}`}
      />
      <div className="relative z-10">
        <div className="mb-4 inline-flex rounded-2xl bg-gradient-to-br from-violet-500/10 to-cyan-500/10 p-3">
          <Icon className="h-5 w-5 text-violet-600" strokeWidth={1.5} />
        </div>
        <h3 className="mb-2 text-base font-semibold tracking-[-0.02em] text-slate-900">
          {title}
        </h3>
        <p className="text-sm leading-relaxed text-slate-500 group-hover:text-slate-600">
          {description}
        </p>
      </div>
    </div>
  );
}

export function LandingV3() {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  return (
    <div className="relative min-h-screen overflow-hidden bg-white text-slate-900 selection:bg-violet-500 selection:text-white">
      {/* Mesh gradient background */}
      <div className="pointer-events-none fixed inset-0">
        <div className="absolute -left-[20%] -top-[30%] h-[800px] w-[800px] rounded-full bg-gradient-to-br from-violet-300/40 via-fuchsia-200/30 to-transparent blur-[100px]" />
        <div className="absolute -right-[15%] top-[10%] h-[600px] w-[600px] rounded-full bg-gradient-to-bl from-cyan-200/40 via-sky-200/25 to-transparent blur-[100px]" />
        <div className="absolute bottom-0 left-[20%] h-[500px] w-[700px] rounded-full bg-gradient-to-t from-amber-100/30 via-rose-100/20 to-transparent blur-[100px]" />
        {/* Animated orbs */}
        <div
          className="absolute left-[10%] top-[40%] h-48 w-48 rounded-full bg-violet-400/15 blur-[80px]"
          style={{ animation: "float 20s ease-in-out infinite" }}
        />
        <div
          className="absolute right-[15%] top-[60%] h-36 w-36 rounded-full bg-cyan-400/15 blur-[60px]"
          style={{ animation: "float 15s ease-in-out infinite reverse" }}
        />
      </div>

      <style jsx>{`
        @keyframes float {
          0%, 100% { transform: translate(0, 0); }
          25% { transform: translate(30px, -40px); }
          50% { transform: translate(-20px, 20px); }
          75% { transform: translate(40px, 30px); }
        }
        @keyframes shimmer {
          0% { background-position: -200% 0; }
          100% { background-position: 200% 0; }
        }
      `}</style>

      {/* Nav */}
      <nav
        className={`fixed top-0 z-50 w-full transition-all duration-700 ${
          mounted ? "translate-y-0 opacity-100" : "-translate-y-4 opacity-0"
        }`}
      >
        <div className="mx-auto max-w-7xl px-6 py-4">
          <div className="flex items-center justify-between rounded-2xl border border-white/40 bg-white/60 px-5 py-3 shadow-lg shadow-violet-500/[0.03] backdrop-blur-xl">
            <div className="flex items-center gap-2.5">
              <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-gradient-to-br from-violet-500 to-cyan-500 text-xs font-bold text-white">
                T
              </div>
              <span className="text-sm font-semibold text-slate-800">
                Talmudpedia
              </span>
            </div>
            <div className="hidden items-center gap-8 md:flex">
              <span className="cursor-pointer text-sm text-slate-500 transition-colors hover:text-slate-900">
                Product
              </span>
              <span className="cursor-pointer text-sm text-slate-500 transition-colors hover:text-slate-900">
                Solutions
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
              className="rounded-xl bg-gradient-to-r from-violet-500 to-cyan-500 px-5 py-2 text-sm font-medium text-white shadow-md shadow-violet-500/20 transition-all duration-300 hover:shadow-lg hover:shadow-violet-500/30"
            >
              Get started
            </Link>
          </div>
        </div>
      </nav>

      {/* Hero */}
      <section className="relative flex min-h-screen flex-col items-center justify-center px-6 pt-28">
        <div
          className={`mx-auto max-w-4xl text-center transition-all duration-1000 delay-200 ${
            mounted ? "translate-y-0 opacity-100" : "translate-y-12 opacity-0"
          }`}
        >
          {/* Badge */}
          <div className="mb-8 inline-flex items-center gap-2 rounded-full border border-violet-200 bg-violet-50 px-4 py-1.5">
            <Sparkles className="h-3.5 w-3.5 text-violet-500" />
            <span className="text-xs font-medium text-violet-600">
              AI-native platform — now in beta
            </span>
          </div>

          <h1 className="text-5xl font-bold leading-[1.05] tracking-[-0.04em] text-slate-900 md:text-7xl lg:text-8xl">
            The platform
            <br />
            for{" "}
            <span
              className="bg-gradient-to-r from-violet-500 via-fuchsia-500 to-cyan-500 bg-clip-text text-transparent"
              style={{
                backgroundSize: "200% auto",
                animation: "shimmer 4s linear infinite",
              }}
            >
              AI builders
            </span>
          </h1>

          <p className="mx-auto mt-8 max-w-2xl text-lg leading-relaxed text-slate-500">
            Design agents as graphs. Build RAG pipelines visually. Ship
            applications with embedded intelligence. All governed, all
            traced, all in one place.
          </p>

          <div className="mt-10 flex flex-col items-center gap-3 sm:flex-row sm:justify-center">
            <Link
              href="/auth/login"
              className="group flex items-center gap-2 rounded-2xl bg-gradient-to-r from-violet-500 to-cyan-500 px-8 py-4 text-sm font-semibold text-white shadow-xl shadow-violet-500/20 transition-all duration-300 hover:-translate-y-0.5 hover:shadow-2xl hover:shadow-violet-500/30"
            >
              Start building free
              <ArrowRight className="h-4 w-4 transition-transform duration-300 group-hover:translate-x-1" />
            </Link>
            <Link
              href="/admin/apps"
              className="flex items-center gap-2 rounded-2xl border border-slate-200 bg-white/80 px-8 py-4 text-sm font-medium text-slate-700 backdrop-blur-xl transition-all duration-300 hover:border-slate-300 hover:bg-white"
            >
              <Zap className="h-4 w-4 text-amber-500" />
              Live demo
            </Link>
          </div>

          {/* Trust logos placeholder */}
          <div className="mt-20 flex flex-col items-center gap-4">
            <p className="text-xs tracking-[0.15em] text-slate-400">
              TRUSTED BY TEAMS BUILDING THE FUTURE
            </p>
            <div className="flex items-center gap-10">
              {["Team A", "Team B", "Team C", "Team D"].map((t) => (
                <span key={t} className="text-sm font-medium text-slate-300">
                  {t}
                </span>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="relative px-6 pb-32 pt-16">
        <div className="mx-auto max-w-6xl">
          <div className="mb-16 text-center">
            <p className="mb-3 text-xs font-semibold tracking-[0.2em] text-violet-500">
              PLATFORM CAPABILITIES
            </p>
            <h2 className="text-4xl font-bold tracking-[-0.03em] text-slate-900 md:text-5xl">
              Everything, unified
            </h2>
          </div>

          <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-3">
            <FloatingCard
              icon={Workflow}
              title="Agent graph authoring"
              description="Design reasoning flows as composable directed graphs. Mix logic, tools, retrieval, and orchestration into powerful agents."
              gradient="bg-gradient-to-br from-violet-50/80 to-transparent"
              delay="0ms"
            />
            <FloatingCard
              icon={Database}
              title="RAG pipeline builder"
              description="From raw data to retrievable knowledge. Ingest, chunk, embed, and query with visual graph operators."
              gradient="bg-gradient-to-br from-cyan-50/80 to-transparent"
              delay="100ms"
            />
            <FloatingCard
              icon={Blocks}
              title="Artifact extensions"
              description="Deploy custom code to the edge. Artifact-backed tools, agent nodes, and RAG operators execute on Cloudflare Workers."
              gradient="bg-gradient-to-br from-fuchsia-50/80 to-transparent"
              delay="200ms"
            />
            <FloatingCard
              icon={Cpu}
              title="Model registry"
              description="Manage models across every provider. Routing, fallbacks, usage tracking, and governance — all unified."
              gradient="bg-gradient-to-br from-amber-50/80 to-transparent"
              delay="300ms"
            />
            <FloatingCard
              icon={Layers}
              title="Published apps"
              description="Ship complete AI applications with PRICO widget layouts, embedded agents, and custom interactive surfaces."
              gradient="bg-gradient-to-br from-rose-50/80 to-transparent"
              delay="400ms"
            />
            <FloatingCard
              icon={Shield}
              title="Governance & tenancy"
              description="Enterprise-grade from day one. Multi-tenant isolation, audit trails, tracing, and policy anchoring built in."
              gradient="bg-gradient-to-br from-emerald-50/80 to-transparent"
              delay="500ms"
            />
          </div>
        </div>
      </section>

      {/* Product showcase */}
      <section className="relative px-6 pb-32">
        <div className="mx-auto max-w-6xl">
          <div className="overflow-hidden rounded-[2rem] border border-white/40 bg-gradient-to-br from-violet-500 to-cyan-500 p-[1px] shadow-2xl shadow-violet-500/10">
            <div className="rounded-[calc(2rem-1px)] bg-white p-8 md:p-12">
              <div className="grid gap-12 md:grid-cols-2">
                <div>
                  <p className="mb-3 text-xs font-semibold tracking-[0.2em] text-violet-500">
                    ARCHITECTURE
                  </p>
                  <h2 className="mb-6 text-3xl font-bold tracking-[-0.03em] text-slate-900 md:text-4xl">
                    Five layers,
                    <br />
                    one platform
                  </h2>
                  <p className="text-[15px] leading-relaxed text-slate-500">
                    Every layer is purpose-built with clear boundaries. Foundation
                    handles identity. Resources manage models and tools. RAG builds
                    knowledge. Agents reason. Apps deliver.
                  </p>
                </div>
                <div className="flex flex-col gap-3">
                  {[
                    { name: "Applications", color: "from-violet-500 to-fuchsia-500", w: "w-full" },
                    { name: "Agent Execution", color: "from-fuchsia-500 to-pink-500", w: "w-[90%]" },
                    { name: "RAG & Knowledge", color: "from-pink-500 to-rose-500", w: "w-[80%]" },
                    { name: "Shared Resources", color: "from-rose-400 to-amber-400", w: "w-[70%]" },
                    { name: "Platform Foundation", color: "from-amber-400 to-yellow-400", w: "w-[60%]" },
                  ].map((l) => (
                    <div
                      key={l.name}
                      className={`${l.w} rounded-xl bg-gradient-to-r ${l.color} px-5 py-3 text-sm font-medium text-white shadow-md transition-all duration-300 hover:-translate-y-0.5`}
                    >
                      {l.name}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Stats */}
      <section className="relative px-6 pb-32">
        <div className="mx-auto grid max-w-4xl gap-6 md:grid-cols-3">
          {[
            { value: "< 200ms", label: "Agent cold-start", icon: Zap },
            { value: "5 layers", label: "Clear architecture", icon: Layers },
            { value: "100%", label: "Tenant isolation", icon: Shield },
          ].map((stat) => (
            <div
              key={stat.label}
              className="rounded-3xl border border-white/40 bg-white/70 p-8 text-center shadow-lg backdrop-blur-xl transition-all duration-300 hover:-translate-y-1 hover:shadow-xl"
            >
              <stat.icon className="mx-auto mb-3 h-5 w-5 text-violet-500" />
              <div className="mb-1 text-3xl font-bold tracking-[-0.03em] text-slate-900">
                {stat.value}
              </div>
              <div className="text-sm text-slate-500">{stat.label}</div>
            </div>
          ))}
        </div>
      </section>

      {/* CTA */}
      <section className="relative px-6 pb-40">
        <div className="mx-auto max-w-3xl text-center">
          <h2 className="mb-6 text-4xl font-bold tracking-[-0.03em] text-slate-900 md:text-6xl">
            Build the future
            <br />
            <span className="bg-gradient-to-r from-violet-500 to-cyan-500 bg-clip-text text-transparent">
              of AI applications
            </span>
          </h2>
          <p className="mx-auto mb-10 max-w-lg text-base text-slate-500">
            Join the platform where teams build, compose, and deploy intelligent
            systems at scale.
          </p>
          <Link
            href="/auth/login"
            className="group inline-flex items-center gap-2 rounded-2xl bg-gradient-to-r from-violet-500 to-cyan-500 px-10 py-4 text-sm font-semibold text-white shadow-xl shadow-violet-500/20 transition-all duration-300 hover:-translate-y-0.5 hover:shadow-2xl hover:shadow-violet-500/30"
          >
            Start for free
            <ArrowRight className="h-4 w-4 transition-transform duration-300 group-hover:translate-x-1" />
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-slate-100 px-6 py-10">
        <div className="mx-auto flex max-w-6xl flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div className="flex items-center gap-2.5">
            <div className="flex h-6 w-6 items-center justify-center rounded-lg bg-gradient-to-br from-violet-500 to-cyan-500 text-[10px] font-bold text-white">
              T
            </div>
            <span className="text-sm font-semibold text-slate-700">Talmudpedia</span>
          </div>
          <span className="text-sm text-slate-400">© 2026 Talmudpedia. All rights reserved.</span>
        </div>
      </footer>
    </div>
  );
}
