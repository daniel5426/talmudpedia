"use client";

import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import { ChevronDown, ArrowRight } from "lucide-react";

const screenshots = {
  dashboard: "/platform_screenshot/Screenshot 2026-03-23 at 22.49.10.png",
  stats: "/platform_screenshot/Screenshot 2026-03-23 at 22.49.30.png",
  artifacts: "/platform_screenshot/Screenshot 2026-03-23 at 22.50.52.png",
  builder: "/platform_screenshot/Screenshot 2026-03-23 at 22.58.34.png",
  agents: "/platform_screenshot/Screenshot 2026-03-23 at 22.59.00.png",
  prompts: "/platform_screenshot/Screenshot 2026-03-23 at 23.00.07.png",
  apps: "/platform_screenshot/Screenshot 2026-03-23 at 23.00.26.png",
};

/* ── Scroll-reveal hook ── */
function useScrollReveal() {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("revealed");
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.15, rootMargin: "0px 0px -60px 0px" }
    );

    const targets = el.querySelectorAll("[data-reveal]");
    targets.forEach((t) => observer.observe(t));

    return () => observer.disconnect();
  }, []);

  return ref;
}

export function LandingV9() {
  const [scrolled, setScrolled] = useState(false);
  const pageRef = useScrollReveal();

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 40);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <div
      ref={pageRef}
      className="min-h-screen bg-white font-sans overflow-x-hidden selection:bg-black/10"
    >
      {/* ── Animation keyframes ── */}
      <style>{`
        /* Hero entrance — staggered */
        @keyframes heroFadeUp {
          from { opacity: 0; transform: translateY(28px); }
          to { opacity: 1; transform: translateY(0); }
        }
        @keyframes heroFadeIn {
          from { opacity: 0; }
          to { opacity: 1; }
        }
        @keyframes heroScale {
          from { opacity: 0; transform: scale(0.96) translateY(20px); }
          to { opacity: 1; transform: scale(1) translateY(0); }
        }
        .hero-1 { animation: heroFadeUp 0.9s cubic-bezier(0.16,1,0.3,1) 0.1s both; }
        .hero-2 { animation: heroFadeUp 0.9s cubic-bezier(0.16,1,0.3,1) 0.25s both; }
        .hero-3 { animation: heroFadeUp 0.9s cubic-bezier(0.16,1,0.3,1) 0.4s both; }
        .hero-4 { animation: heroFadeUp 0.9s cubic-bezier(0.16,1,0.3,1) 0.55s both; }
        .hero-5 { animation: heroFadeIn 1s ease-out 0.7s both; }
        .hero-6 { animation: heroScale 1.2s cubic-bezier(0.16,1,0.3,1) 0.8s both; }

        /* Ambient breathing */
        @keyframes breathe {
          0%, 100% { transform: scale(1); opacity: 1; }
          50% { transform: scale(1.08); opacity: 0.7; }
        }
        .animate-breathe { animation: breathe 6s ease-in-out infinite; }
        .animate-breathe-slow { animation: breathe 8s ease-in-out infinite; }

        /* Scroll reveal */
        [data-reveal] {
          opacity: 0;
          transform: translateY(40px);
          transition: opacity 0.8s cubic-bezier(0.16,1,0.3,1), transform 0.8s cubic-bezier(0.16,1,0.3,1);
        }
        [data-reveal].revealed {
          opacity: 1;
          transform: translateY(0);
        }
        [data-reveal="scale"] {
          opacity: 0;
          transform: scale(0.95);
          transition: opacity 0.9s cubic-bezier(0.16,1,0.3,1), transform 0.9s cubic-bezier(0.16,1,0.3,1);
        }
        [data-reveal="scale"].revealed {
          opacity: 1;
          transform: scale(1);
        }
        [data-reveal="left"] {
          opacity: 0;
          transform: translateX(-40px);
          transition: opacity 0.8s cubic-bezier(0.16,1,0.3,1), transform 0.8s cubic-bezier(0.16,1,0.3,1);
        }
        [data-reveal="left"].revealed {
          opacity: 1;
          transform: translateX(0);
        }
        [data-reveal="right"] {
          opacity: 0;
          transform: translateX(40px);
          transition: opacity 0.8s cubic-bezier(0.16,1,0.3,1), transform 0.8s cubic-bezier(0.16,1,0.3,1);
        }
        [data-reveal="right"].revealed {
          opacity: 1;
          transform: translateX(0);
        }

        /* Stagger children */
        [data-reveal-delay="1"] { transition-delay: 0.1s; }
        [data-reveal-delay="2"] { transition-delay: 0.2s; }
        [data-reveal-delay="3"] { transition-delay: 0.3s; }

        /* Screenshot hover lift */
        .screenshot-hover {
          transition: transform 0.5s cubic-bezier(0.16,1,0.3,1), box-shadow 0.5s ease;
        }
        .screenshot-hover:hover {
          transform: translateY(-4px);
          box-shadow: 0 24px 80px -12px rgba(0,0,0,0.12);
        }
      `}</style>

      {/* ── Nav — transparent → floating pill on scroll ── */}
      <nav
        className={`fixed top-0 z-50 w-full transition-all duration-500 ease-out ${
          scrolled ? "pt-3 px-4 md:px-8" : ""
        }`}
      >
        <div
          className={`mx-auto flex items-center h-14 transition-all duration-500 ease-out ${
            scrolled
              ? "max-w-4xl bg-white/90 backdrop-blur-xl rounded-full shadow-[0_4px_24px_-4px_rgba(0,0,0,0.08)] border border-gray-200/60 px-5"
              : "max-w-[1200px] bg-transparent px-6"
          }`}
        >
          <Link href="/" className="flex items-center gap-2.5">
            <img
              src="/kesher.png"
              alt="Talmudpedia"
              className="w-7 h-7 rounded-lg"
            />
            <span className="text-lg font-bold tracking-tight text-black">
              Talmudpedia
            </span>
          </Link>

          <div className="flex-1" />

          <div className="hidden md:flex items-center gap-6 text-[13px] font-medium text-[#4b5563]">
            <button className="flex items-center gap-1 hover:text-black transition-colors">
              Platform <ChevronDown className="w-3.5 h-3.5 opacity-60" />
            </button>
            <Link href="#" className="hover:text-black transition-colors">
              Agents
            </Link>
            <Link href="#" className="hover:text-black transition-colors">
              Apps
            </Link>
            <Link href="#" className="hover:text-black transition-colors">
              Docs
            </Link>
            <Link href="#" className="hover:text-black transition-colors">
              Pricing
            </Link>
          </div>

          <div className="flex-1" />

          <div className="flex items-center gap-3">
            <Link
              href="/auth/login"
              className="hidden sm:block text-[13px] font-medium text-[#4b5563] hover:text-black transition-colors px-3 py-1.5"
            >
              Log in
            </Link>
            <Link
              href="/auth/login"
              className="px-4 py-2 bg-black text-white hover:bg-gray-900 text-[13px] font-medium rounded-full transition-colors"
            >
              Start building
            </Link>
          </div>
        </div>
      </nav>

      {/* ── Hero ── */}
      <section className="relative bg-[#0a0a0a] overflow-hidden">
        {/* White arch — seamlessly marries the nav area */}
        <div className="absolute top-0 left-0 right-0 z-10 pointer-events-none">
          <svg
            viewBox="0 0 1440 80"
            fill="none"
            className="w-full"
            preserveAspectRatio="none"
          >
            <path
              d="M0 0H1440V40C1440 40 1200 80 720 80C240 80 0 40 0 40V0Z"
              fill="white"
            />
          </svg>
        </div>

        {/* Grid overlay */}
        <div className="absolute inset-0 bg-[linear-gradient(to_right,#ffffff08_1px,transparent_1px),linear-gradient(to_bottom,#ffffff08_1px,transparent_1px)] bg-[size:48px_48px] [mask-image:radial-gradient(ellipse_80%_50%_at_50%_30%,black_20%,transparent_100%)]" />

        {/* Ambient glows — breathing */}
        <div className="absolute top-[15%] left-1/2 -translate-x-1/2 w-[700px] h-[400px] bg-white/[0.03] blur-[140px] rounded-full pointer-events-none animate-breathe" />
        <div className="absolute top-[45%] left-[20%] w-[300px] h-[300px] bg-emerald-500/[0.02] blur-[100px] rounded-full pointer-events-none animate-breathe-slow" />
        <div className="absolute top-[30%] right-[15%] w-[250px] h-[250px] bg-blue-500/[0.02] blur-[100px] rounded-full pointer-events-none animate-breathe" />

        {/* Hero text — staggered entrance */}
        <div className="relative z-20 flex flex-col items-center text-center px-6 pt-36 pb-16">
          <div className="hero-1 inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full border border-white/10 bg-white/[0.04] backdrop-blur-md mb-8">
            <span className="flex h-2 w-2 rounded-full bg-[#22c55e] animate-pulse" />
            <span className="text-[12px] font-medium tracking-wide text-white/70 uppercase">
              Multi-tenant AI Platform
            </span>
          </div>

          <h1 className="hero-2 text-[48px] sm:text-[56px] md:text-[68px] font-medium tracking-tight text-white leading-[1.05] mb-6">
            Your AI operations,
            <br />
            one dashboard.
          </h1>

          <p className="hero-3 text-[17px] md:text-[18px] text-[#a1a1aa] max-w-2xl leading-relaxed mb-10">
            Talmudpedia gives teams a single surface to build agents, manage
            knowledge pipelines, and govern every token in production.
          </p>

          <div className="hero-4 flex flex-col sm:flex-row items-center gap-4 mb-12">
            <Link
              href="/auth/login"
              className="px-7 py-3.5 bg-white text-black hover:bg-gray-100 text-[14px] font-medium rounded-full transition-all duration-300 flex items-center gap-2 group shadow-[0_0_30px_rgba(255,255,255,0.1)] hover:shadow-[0_0_40px_rgba(255,255,255,0.2)]"
            >
              Start building
              <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform duration-300" />
            </Link>
            <Link
              href="/admin/apps"
              className="px-7 py-3.5 bg-white/10 border border-white/10 hover:bg-white/15 hover:border-white/20 text-white text-[14px] font-medium rounded-full transition-all duration-300 backdrop-blur-md"
            >
              View documentation
            </Link>
          </div>

          <div className="hero-5 flex flex-wrap justify-center gap-3">
            {["586 agent runs", "94.4% success", "1.56M tokens processed"].map(
              (label) => (
                <div
                  key={label}
                  className="px-3.5 py-1.5 rounded-full border border-white/10 bg-white/[0.04] text-[12px] text-white/50 font-medium"
                >
                  {label}
                </div>
              )
            )}
          </div>
        </div>

        {/* Hero Screenshot — real dashboard with edge fades */}
        <div className="hero-6 relative w-full max-w-[1100px] mx-auto px-4 md:px-6 z-20 mt-4">
          {/* Side gradient fades */}
          <div className="absolute top-0 left-0 w-16 md:w-28 h-full bg-gradient-to-r from-[#0a0a0a] to-transparent z-30 pointer-events-none" />
          <div className="absolute top-0 right-0 w-16 md:w-28 h-full bg-gradient-to-l from-[#0a0a0a] to-transparent z-30 pointer-events-none" />
          {/* Bottom fade — transitions into white section below */}
          <div className="absolute bottom-0 left-0 right-0 h-48 bg-gradient-to-b from-transparent via-white/60 to-white z-30 pointer-events-none" />

          <div className="rounded-t-[16px] md:rounded-t-[24px] overflow-hidden shadow-2xl shadow-black/40">
            <img
              src={screenshots.dashboard}
              alt="Talmudpedia Dashboard"
              className="w-full block"
              loading="eager"
            />
          </div>
        </div>
      </section>

      {/* ── Agents Section ── */}
      <section className="relative py-24 md:py-32 px-6 bg-white overflow-hidden">
        {/* Dot grid texture */}
        <div className="absolute inset-0 bg-[radial-gradient(#e5e7eb_1px,transparent_1px)] bg-[size:24px_24px] opacity-40 [mask-image:radial-gradient(ellipse_60%_60%_at_50%_50%,black,transparent)]" />

        <div className="relative max-w-[1100px] mx-auto">
          <div className="grid md:grid-cols-2 gap-12 md:gap-16 items-center">
            {/* Text — slides in from left */}
            <div data-reveal="left">
              <div className="text-[12px] font-semibold text-emerald-600 uppercase tracking-[0.15em] mb-4">
                Agents Management
              </div>
              <h2 className="text-[32px] md:text-[40px] font-medium tracking-tight text-gray-900 leading-[1.1] mb-5">
                Build, version, and deploy AI agents
              </h2>
              <p className="text-[16px] text-gray-500 leading-relaxed mb-8">
                Every agent is a versioned graph. Define reasoning steps, connect
                tools, attach knowledge sources, and publish with one click.
                Monitor threads, success rates, and cost per run from a single
                view.
              </p>
              <Link
                href="/admin/agents"
                className="inline-flex items-center gap-2 text-[14px] font-medium text-black hover:gap-3 transition-all duration-300"
              >
                Explore agents <ArrowRight className="w-4 h-4" />
              </Link>
            </div>

            {/* Screenshot — slides in from right with glow */}
            <div data-reveal="right" className="relative">
              <div className="absolute -inset-6 bg-gradient-to-br from-emerald-100/50 via-transparent to-blue-100/30 rounded-[2rem] blur-2xl pointer-events-none" />
              <div className="relative rounded-2xl overflow-hidden shadow-xl shadow-black/[0.06] border border-gray-200/80 screenshot-hover">
                <img
                  src={screenshots.agents}
                  alt="Agents Management"
                  className="w-full block"
                  loading="lazy"
                />
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── Builder Section ── */}
      <section className="relative py-24 md:py-32 px-6 bg-[#fafafa] overflow-hidden">
        {/* Gradient border lines */}
        <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-gray-300 to-transparent" />
        <div className="absolute bottom-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-gray-300 to-transparent" />

        <div className="relative max-w-[1100px] mx-auto">
          <div className="grid md:grid-cols-2 gap-12 md:gap-16 items-center">
            {/* Screenshot — slides in from left */}
            <div
              data-reveal="left"
              className="relative order-2 md:order-1"
            >
              <div className="absolute -inset-6 bg-gradient-to-tl from-purple-100/50 via-transparent to-amber-100/30 rounded-[2rem] blur-2xl pointer-events-none" />
              <div className="relative rounded-2xl overflow-hidden shadow-xl shadow-black/[0.06] border border-gray-200/80 screenshot-hover">
                <img
                  src={screenshots.builder}
                  alt="Agent Graph Builder"
                  className="w-full block"
                  loading="lazy"
                />
              </div>
            </div>

            {/* Text — slides in from right */}
            <div data-reveal="right" className="order-1 md:order-2">
              <div className="text-[12px] font-semibold text-purple-600 uppercase tracking-[0.15em] mb-4">
                Graph Builder
              </div>
              <h2 className="text-[32px] md:text-[40px] font-medium tracking-tight text-gray-900 leading-[1.1] mb-5">
                Visual agent orchestration
              </h2>
              <p className="text-[16px] text-gray-500 leading-relaxed mb-8">
                Drag-and-drop node composition with built-in reasoning,
                retrieval, and tool execution. Each graph is version-controlled
                and deployable with one click.
              </p>
              <Link
                href="/admin/agents"
                className="inline-flex items-center gap-2 text-[14px] font-medium text-black hover:gap-3 transition-all duration-300"
              >
                Open the builder <ArrowRight className="w-4 h-4" />
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* ── Stats Section — full-width showcase ── */}
      <section className="relative py-24 md:py-32 px-6 bg-white overflow-hidden">
        <div className="relative max-w-[1200px] mx-auto">
          <div data-reveal className="text-center mb-16">
            <div className="text-[12px] font-semibold text-amber-600 uppercase tracking-[0.15em] mb-4">
              Observability
            </div>
            <h2 className="text-[32px] md:text-[44px] font-medium tracking-tight text-gray-900 mb-4">
              Full visibility into every token
            </h2>
            <p className="text-[17px] text-gray-500 max-w-xl mx-auto">
              Track usage, spend, agent performance, and pipeline health from a
              single analytics surface.
            </p>
          </div>

          {/* Screenshot with edge fades and glow */}
          <div data-reveal="scale" className="relative">
            <div className="absolute -inset-8 bg-gradient-to-b from-amber-100/40 via-transparent to-transparent rounded-[2rem] blur-3xl pointer-events-none" />

            {/* Side fades */}
            <div className="absolute top-0 left-0 w-12 md:w-20 h-full bg-gradient-to-r from-white to-transparent z-10 pointer-events-none" />
            <div className="absolute top-0 right-0 w-12 md:w-20 h-full bg-gradient-to-l from-white to-transparent z-10 pointer-events-none" />
            {/* Bottom fade */}
            <div className="absolute bottom-0 left-0 right-0 h-20 bg-gradient-to-b from-transparent to-white z-10 pointer-events-none" />

            <div className="relative rounded-2xl overflow-hidden shadow-xl shadow-black/[0.06] border border-gray-200/80">
              <img
                src={screenshots.stats}
                alt="Platform Analytics"
                className="w-full block"
                loading="lazy"
              />
            </div>
          </div>
        </div>
      </section>

      {/* ── Artifacts Section — dark for contrast ── */}
      <section className="relative py-24 md:py-32 px-6 bg-[#0a0a0a] overflow-hidden">
        {/* Grid texture */}
        <div className="absolute inset-0 bg-[linear-gradient(to_right,#ffffff05_1px,transparent_1px),linear-gradient(to_bottom,#ffffff05_1px,transparent_1px)] bg-[size:48px_48px] [mask-image:radial-gradient(ellipse_50%_50%_at_50%_50%,black,transparent)]" />

        {/* Ambient glow */}
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[400px] bg-blue-500/[0.04] blur-[120px] rounded-full pointer-events-none animate-breathe-slow" />

        <div className="relative max-w-[1100px] mx-auto">
          <div className="grid md:grid-cols-2 gap-12 md:gap-16 items-center">
            <div data-reveal="left">
              <div className="text-[12px] font-semibold text-blue-400 uppercase tracking-[0.15em] mb-4">
                Code Artifacts
              </div>
              <h2 className="text-[32px] md:text-[40px] font-medium tracking-tight text-white leading-[1.1] mb-5">
                Extend with custom code
              </h2>
              <p className="text-[16px] text-white/50 leading-relaxed mb-8">
                Write Python functions, tool integrations, and custom workers
                directly in the platform. Each artifact is versioned, testable,
                and deployable alongside your agents.
              </p>
              <Link
                href="/admin/apps"
                className="inline-flex items-center gap-2 text-[14px] font-medium text-white hover:gap-3 transition-all duration-300"
              >
                View artifacts <ArrowRight className="w-4 h-4" />
              </Link>
            </div>

            <div data-reveal="right" className="relative">
              <div className="absolute -inset-6 bg-gradient-to-br from-blue-500/10 via-transparent to-purple-500/10 rounded-[2rem] blur-2xl pointer-events-none" />
              <div className="relative rounded-2xl overflow-hidden shadow-2xl shadow-black/40 border border-white/10 screenshot-hover">
                <img
                  src={screenshots.artifacts}
                  alt="Code Artifacts"
                  className="w-full block"
                  loading="lazy"
                />
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── Apps & Prompts — side-by-side screenshots ── */}
      <section className="relative py-24 md:py-32 px-6 bg-white overflow-hidden">
        <div className="absolute inset-0 bg-[radial-gradient(#e5e7eb_1px,transparent_1px)] bg-[size:32px_32px] opacity-30 [mask-image:linear-gradient(to_bottom,transparent,black_20%,black_80%,transparent)]" />

        <div className="relative max-w-[1100px] mx-auto">
          <div data-reveal className="text-center mb-16">
            <h2 className="text-[32px] md:text-[44px] font-medium tracking-tight text-gray-900 mb-4">
              Apps and prompts, all in one place
            </h2>
            <p className="text-[17px] text-gray-500 max-w-xl mx-auto">
              Publish agent-backed applications and maintain a shared prompt
              library across your organization.
            </p>
          </div>

          <div className="grid md:grid-cols-2 gap-8">
            {/* Apps */}
            <div data-reveal data-reveal-delay="1" className="relative group">
              <div className="absolute -inset-3 bg-gradient-to-br from-emerald-100/40 to-transparent rounded-[2rem] blur-xl opacity-0 group-hover:opacity-100 transition-opacity duration-500 pointer-events-none" />
              <div className="relative rounded-2xl overflow-hidden shadow-lg shadow-black/[0.04] border border-gray-200/80 screenshot-hover">
                <img
                  src={screenshots.apps}
                  alt="Published Apps"
                  className="w-full block"
                  loading="lazy"
                />
              </div>
              <div className="mt-5 text-center">
                <div className="text-[15px] font-medium text-gray-900">
                  Published Apps
                </div>
                <div className="text-[13px] text-gray-500 mt-1">
                  Deploy and manage agent-powered applications
                </div>
              </div>
            </div>

            {/* Prompts */}
            <div data-reveal data-reveal-delay="2" className="relative group">
              <div className="absolute -inset-3 bg-gradient-to-br from-purple-100/40 to-transparent rounded-[2rem] blur-xl opacity-0 group-hover:opacity-100 transition-opacity duration-500 pointer-events-none" />
              <div className="relative rounded-2xl overflow-hidden shadow-lg shadow-black/[0.04] border border-gray-200/80 screenshot-hover">
                <img
                  src={screenshots.prompts}
                  alt="Prompt Library"
                  className="w-full block"
                  loading="lazy"
                />
              </div>
              <div className="mt-5 text-center">
                <div className="text-[15px] font-medium text-gray-900">
                  Prompt Library
                </div>
                <div className="text-[13px] text-gray-500 mt-1">
                  Shared, versioned prompts across all agents
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── Metrics ── */}
      <section className="py-16 md:py-20 px-6 bg-white">
        <div data-reveal="scale" className="max-w-[1100px] mx-auto">
          <div className="rounded-3xl border border-gray-200 bg-[#fafafa] p-8 md:p-12">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-8 md:gap-4 text-center">
              {[
                { value: "586", label: "Agent runs" },
                { value: "94.4%", label: "Success rate" },
                { value: "1.56M", label: "Tokens governed" },
                { value: "< 120ms", label: "Median latency" },
              ].map((m) => (
                <div key={m.label}>
                  <div className="text-[36px] md:text-[48px] font-semibold tracking-tight text-black leading-none">
                    {m.value}
                  </div>
                  <div className="text-[13px] text-gray-500 mt-2">
                    {m.label}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ── CTA ── */}
      <section className="py-24 md:py-32 px-6 bg-white">
        <div data-reveal className="max-w-3xl mx-auto text-center">
          <h2 className="text-[36px] md:text-[44px] font-medium tracking-tight text-gray-900 mb-5">
            Start building with Talmudpedia
          </h2>
          <p className="text-[17px] text-gray-500 max-w-xl mx-auto mb-10 leading-relaxed">
            Deploy your first agent in minutes. No infrastructure to manage, no
            vendor lock-in, full visibility into every token.
          </p>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <Link
              href="/auth/login"
              className="px-7 py-3.5 bg-black text-white hover:bg-gray-900 text-[14px] font-medium rounded-full transition-all duration-300 flex items-center gap-2 group hover:shadow-[0_8px_32px_-4px_rgba(0,0,0,0.3)]"
            >
              Start building
              <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform duration-300" />
            </Link>
            <Link
              href="/admin/apps"
              className="px-7 py-3.5 bg-white border border-gray-200 hover:bg-gray-50 hover:border-gray-300 text-gray-900 text-[14px] font-medium rounded-full transition-all duration-300"
            >
              View documentation
            </Link>
          </div>
        </div>
      </section>

      {/* ── Footer ── */}
      <footer className="border-t border-gray-100 py-8 px-6">
        <div className="max-w-[1100px] mx-auto flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <img
              src="/kesher.png"
              alt="Talmudpedia"
              className="w-5 h-5 rounded"
            />
            <span className="text-[13px] font-medium text-gray-500">
              Talmudpedia
            </span>
          </div>
          <span className="text-[12px] text-gray-400">
            Built for production AI teams
          </span>
        </div>
      </footer>
    </div>
  );
}
