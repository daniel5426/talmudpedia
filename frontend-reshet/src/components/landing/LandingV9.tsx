"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { ChevronDown, ArrowRight } from "lucide-react";

import {
  ExpandableFeaturesLarge,
  ExpandableFeaturesVertical,
} from "./v9/ExpandableFeatures";
import {
  ExpandableFeaturesCards,
  FeaturesCode,
} from "./v9/FeatureShowcase";
import {
  ContentSection,
  LogoCloud,
  TestimonialSection,
} from "./v9/SocialProof";

const screenshots = {
  dashboard: "/platform_screenshot/Screenshot 2026-03-23 at 22.49.10.png",
};

export function LandingV9() {
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 40);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <div className="min-h-screen bg-white font-sans overflow-x-hidden selection:bg-black/10">
      <style>{`
        html { scroll-behavior: smooth; }
        @keyframes heroFadeUp {
          from { opacity: 0; transform: translateY(28px); }
          to { opacity: 1; transform: translateY(0); }
        }
        @keyframes heroScale {
          from { opacity: 0; transform: scale(0.96) translateY(20px); }
          to { opacity: 1; transform: scale(1) translateY(0); }
        }
        @keyframes heroFadeIn {
          from { opacity: 0; }
          to { opacity: 1; }
        }
        .hero-1 { animation: heroFadeUp 0.9s cubic-bezier(0.16,1,0.3,1) 0.1s both; }
        .hero-2 { animation: heroFadeUp 0.9s cubic-bezier(0.16,1,0.3,1) 0.25s both; }
        .hero-3 { animation: heroFadeUp 0.9s cubic-bezier(0.16,1,0.3,1) 0.4s both; }
        .hero-4 { animation: heroFadeUp 0.9s cubic-bezier(0.16,1,0.3,1) 0.55s both; }
        .hero-5 { animation: heroFadeIn 1s ease-out 0.7s both; }
        .hero-6 { animation: heroScale 1.2s cubic-bezier(0.16,1,0.3,1) 0.8s both; }
        @keyframes breathe {
          0%, 100% { transform: scale(1); opacity: 1; }
          50% { transform: scale(1.08); opacity: 0.7; }
        }
        .animate-breathe { animation: breathe 6s ease-in-out infinite; }
        .animate-breathe-slow { animation: breathe 8s ease-in-out infinite; }
      `}</style>

      {/* ── Nav ── */}
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
            <img src="/kesher.png" alt="AGENTS24" className="w-7 h-7 rounded-lg" />
            <span className="text-lg font-bold tracking-tight text-black">AGENTS24</span>
          </Link>
          <div className="flex-1" />
          <div className="hidden md:flex items-center gap-6 text-[13px] font-medium text-[#4b5563]">
            <Link href="#platform" className="flex items-center gap-1 hover:text-black transition-colors">
              Platform <ChevronDown className="w-3.5 h-3.5 opacity-60" />
            </Link>
            <Link href="#features" className="hover:text-black transition-colors">Features</Link>
            <Link href="#code" className="hover:text-black transition-colors">API</Link>
            <Link href="#deploy" className="hover:text-black transition-colors">Deploy</Link>
            <Link href="#integrations" className="hover:text-black transition-colors">Integrations</Link>
          </div>
          <div className="flex-1" />
          <div className="flex items-center gap-3">
            <Link href="/auth/login" className="hidden sm:block text-[13px] font-medium text-[#4b5563] hover:text-black transition-colors px-3 py-1.5">
              Log in
            </Link>
            <Link href="/auth/signup" className="px-4 py-2 bg-black text-white hover:bg-gray-900 text-[13px] font-medium rounded-full transition-colors">
              Start building
            </Link>
          </div>
        </div>
      </nav>

      {/* ── Hero ── */}
      <section className="relative bg-[#0a0a0a] overflow-hidden">
        <div className="absolute top-0 left-0 right-0 z-10 pointer-events-none">
          <svg viewBox="0 0 1440 80" fill="none" className="w-full" preserveAspectRatio="none">
            <path d="M0 0H1440V40C1440 40 1200 80 720 80C240 80 0 40 0 40V0Z" fill="white" />
          </svg>
        </div>
        <div className="absolute inset-0 bg-[linear-gradient(to_right,#ffffff08_1px,transparent_1px),linear-gradient(to_bottom,#ffffff08_1px,transparent_1px)] bg-[size:48px_48px] [mask-image:radial-gradient(ellipse_80%_50%_at_50%_30%,black_20%,transparent_100%)]" />
        <div className="absolute top-[15%] left-1/2 -translate-x-1/2 w-[700px] h-[400px] bg-white/[0.03] blur-[140px] rounded-full pointer-events-none animate-breathe" />
        <div className="absolute top-[45%] left-[20%] w-[300px] h-[300px] bg-emerald-500/[0.02] blur-[100px] rounded-full pointer-events-none animate-breathe-slow" />
        <div className="absolute top-[30%] right-[15%] w-[250px] h-[250px] bg-blue-500/[0.02] blur-[100px] rounded-full pointer-events-none animate-breathe" />

        <div className="relative z-20 flex flex-col items-center text-center px-6 pt-36 pb-16">
          <div className="hero-1 inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full border border-white/10 bg-white/[0.04] backdrop-blur-md mb-8">
            <span className="flex h-2 w-2 rounded-full bg-[#22c55e] animate-pulse" />
            <span className="text-[12px] font-medium tracking-wide text-white/70 uppercase">
              Multi-tenant AI Platform
            </span>
          </div>
          <h1 className="hero-2 text-[48px] sm:text-[56px] md:text-[68px] font-medium tracking-tight text-white leading-[1.05] mb-6">
            Your AI operations,<br />one dashboard.
          </h1>
          <p className="hero-3 text-[17px] md:text-[18px] text-[#a1a1aa] max-w-2xl leading-relaxed mb-10">
            AGENTS24 gives teams a single surface to build agents, manage
            knowledge pipelines, and govern every token in production.
          </p>
          <div className="hero-4 flex flex-col sm:flex-row items-center gap-4 mb-12">
            <Link href="/auth/signup" className="px-7 py-3.5 bg-white text-black hover:bg-gray-100 text-[14px] font-medium rounded-full transition-all duration-300 flex items-center gap-2 group shadow-[0_0_30px_rgba(255,255,255,0.1)] hover:shadow-[0_0_40px_rgba(255,255,255,0.2)]">
              Start building
              <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform duration-300" />
            </Link>
            <Link href="#platform" className="px-7 py-3.5 bg-white/10 border border-white/10 hover:bg-white/15 hover:border-white/20 text-white text-[14px] font-medium rounded-full transition-all duration-300 backdrop-blur-md">
              View platform
            </Link>
          </div>
          <div className="hero-5 flex flex-wrap justify-center gap-3">
            {["586 agent runs", "94.4% success", "1.56M tokens processed"].map((label) => (
              <div key={label} className="px-3.5 py-1.5 rounded-full border border-white/10 bg-white/[0.04] text-[12px] text-white/50 font-medium">
                {label}
              </div>
            ))}
          </div>
        </div>

        <div className="hero-6 relative w-full max-w-[1100px] mx-auto px-6 z-20 mt-8">
          <div className="absolute bottom-0 left-0 right-0 h-40 bg-gradient-to-b from-transparent to-white z-30 pointer-events-none" />
          <div className="rounded-t-[32px] border border-gray-200/80 bg-white/40 p-3 shadow-[0_40px_100px_-20px_rgba(0,0,0,0.1)] backdrop-blur-2xl overflow-hidden">
            <img src={screenshots.dashboard} alt="AGENTS24 Dashboard" className="w-full block rounded-t-[24px]" loading="eager" />
          </div>
        </div>
      </section>

      {/* ── Sections ── */}
      <LogoCloud />
      <div id="platform" className="scroll-mt-20"><ExpandableFeaturesLarge /></div>
      <div id="features" className="scroll-mt-20"><ExpandableFeaturesCards /></div>
      <div id="code" className="scroll-mt-20"><FeaturesCode /></div>
      <div id="deploy" className="scroll-mt-20"><ExpandableFeaturesVertical /></div>
      <div id="integrations" className="scroll-mt-20"><ContentSection /></div>
      <TestimonialSection />

      {/* ── Extended Footer with giant AGENTS24 ── */}
      <footer className="bg-white border-t border-gray-100">
        {/* Top area — links */}
        <div className="max-w-[1100px] mx-auto px-6 py-14">
          <div className="grid grid-cols-2 md:grid-cols-5 gap-10">
            <div className="col-span-2 md:col-span-1">
              <p className="text-2xl md:text-3xl font-semibold tracking-tight text-gray-900 leading-tight">
                Experience
                <br />
                liftoff
              </p>
            </div>
            {[
              { links: [{ label: "Product", href: "#platform" }, { label: "Features", href: "#features" }, { label: "API", href: "#code" }, { label: "Deploy", href: "#deploy" }, { label: "Integrations", href: "#integrations" }] },
              { links: [{ label: "Sign Up", href: "/auth/signup" }, { label: "Log In", href: "/auth/login" }] },
              { links: [{ label: "Agents", href: "#platform" }, { label: "Builder", href: "#platform" }, { label: "Analytics", href: "#features" }] },
              { links: [{ label: "Privacy", href: "#" }, { label: "Terms", href: "#" }, { label: "Security", href: "#" }] },
            ].map((group, gi) => (
              <div key={gi}>
                <ul className="space-y-2.5">
                  {group.links.map((link) => (
                    <li key={link.label}>
                      <Link href={link.href} className="text-sm text-gray-500 hover:text-gray-900 transition-colors">
                        {link.label}
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>

        {/* Giant brand name */}
        <div className="px-6 pb-6">
          <h2
            className="text-[18vw] md:text-[14vw] font-black tracking-tighter text-gray-900 leading-[0.85] select-none"
            style={{ fontFamily: "system-ui, -apple-system, sans-serif" }}
          >
            AGENTS24
          </h2>
        </div>

        {/* Bottom bar */}
        <div className="border-t border-gray-100 px-6 py-5">
          <div className="max-w-[1100px] mx-auto flex flex-col sm:flex-row items-center justify-between gap-3">
            <div className="flex items-center gap-2.5">
              <img src="/kesher.png" alt="AGENTS24" className="w-5 h-5 rounded" />
              <span className="text-xs text-gray-400">AGENTS24</span>
            </div>
            <div className="flex items-center gap-6">
              {["About", "Privacy", "Terms"].map((link) => (
                <Link key={link} href="#" className="text-xs text-gray-400 hover:text-gray-900 transition-colors">
                  {link}
                </Link>
              ))}
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}
