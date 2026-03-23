"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import Link from "next/link";
import {
  ChevronDown,
  ArrowRight,
  Zap,
  Shield,
  BarChart3,
  Layers,
  GitBranch,
  Bot,
  Code2,
  Workflow,
  Eye,
  Sparkles,
  Terminal,
  Globe,
  Lock,
  Cpu,
} from "lucide-react";

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
      { threshold: 0.12, rootMargin: "0px 0px -40px 0px" }
    );
    const targets = el.querySelectorAll("[data-reveal]");
    targets.forEach((t) => observer.observe(t));
    return () => observer.disconnect();
  }, []);
  return ref;
}

/* ── Animated counter hook ── */
function useCountUp(end: number, duration = 2000, startOnView = true) {
  const [count, setCount] = useState(0);
  const ref = useRef<HTMLDivElement>(null);
  const started = useRef(false);

  useEffect(() => {
    if (!startOnView) return;
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting && !started.current) {
          started.current = true;
          const startTime = performance.now();
          const animate = (now: number) => {
            const elapsed = now - startTime;
            const progress = Math.min(elapsed / duration, 1);
            const eased = 1 - Math.pow(1 - progress, 3);
            setCount(Math.floor(eased * end));
            if (progress < 1) requestAnimationFrame(animate);
          };
          requestAnimationFrame(animate);
        }
      },
      { threshold: 0.3 }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [end, duration, startOnView]);

  return { count, ref };
}

/* ── Feature tabs data ── */
const featureTabs = [
  {
    id: "agents",
    label: "Agents",
    icon: Bot,
    color: "#22c55e",
    title: "Build, version, and deploy AI agents",
    desc: "Every agent is a versioned graph. Define reasoning steps, connect tools, attach knowledge sources, and publish with one click.",
    screenshot: screenshots.agents,
  },
  {
    id: "builder",
    label: "Graph Builder",
    icon: Workflow,
    color: "#a855f7",
    title: "Visual agent orchestration",
    desc: "Drag-and-drop node composition with built-in reasoning, retrieval, and tool execution. Each graph is version-controlled.",
    screenshot: screenshots.builder,
  },
  {
    id: "analytics",
    label: "Analytics",
    icon: BarChart3,
    color: "#f59e0b",
    title: "Full visibility into every token",
    desc: "Track usage, spend, agent performance, and pipeline health from a single analytics surface in real time.",
    screenshot: screenshots.stats,
  },
  {
    id: "artifacts",
    label: "Code Artifacts",
    icon: Code2,
    color: "#3b82f6",
    title: "Extend with custom code",
    desc: "Write Python functions, tool integrations, and custom workers directly in the platform. Each artifact is versioned and testable.",
    screenshot: screenshots.artifacts,
  },
];

/* ── Timeline steps ── */
const timelineSteps = [
  {
    num: "01",
    title: "Define your agent graph",
    desc: "Use the visual builder to compose reasoning steps, tool calls, and knowledge retrieval nodes into a directed graph.",
    icon: GitBranch,
    color: "#22c55e",
  },
  {
    num: "02",
    title: "Connect knowledge & tools",
    desc: "Attach vector stores, APIs, databases, and custom Python functions. Everything is versioned alongside your agent.",
    icon: Layers,
    color: "#a855f7",
  },
  {
    num: "03",
    title: "Test & iterate in the playground",
    desc: "Run conversations, inspect traces, debug tool calls, and fine-tune prompts before going live.",
    icon: Eye,
    color: "#f59e0b",
  },
  {
    num: "04",
    title: "Deploy & govern at scale",
    desc: "One-click deploy to production. Monitor every token, set budgets, enforce guardrails, and track ROI automatically.",
    icon: Shield,
    color: "#3b82f6",
  },
];

/* ── Bento items ── */
const bentoItems = [
  {
    title: "Multi-tenant isolation",
    desc: "Each organization gets its own sandboxed environment with separate data, credentials, and rate limits.",
    icon: Lock,
    span: "col-span-1",
    gradient: "from-emerald-500/10 to-teal-500/5",
    iconColor: "text-emerald-500",
  },
  {
    title: "Real-time streaming",
    desc: "Token-by-token streaming with WebSocket support. Sub-120ms median latency across all deployments.",
    icon: Zap,
    span: "md:col-span-2",
    gradient: "from-amber-500/10 to-orange-500/5",
    iconColor: "text-amber-500",
  },
  {
    title: "Agentic code generation",
    desc: "Agents can write, test, and deploy code artifacts autonomously with full audit trails.",
    icon: Terminal,
    span: "md:col-span-2",
    gradient: "from-purple-500/10 to-violet-500/5",
    iconColor: "text-purple-500",
  },
  {
    title: "Global edge deployment",
    desc: "Deploy agents to edge locations worldwide for minimal latency and maximum availability.",
    icon: Globe,
    span: "col-span-1",
    gradient: "from-blue-500/10 to-cyan-500/5",
    iconColor: "text-blue-500",
  },
  {
    title: "Built-in guardrails",
    desc: "Content filtering, token budgets, PII detection, and custom safety policies — all configurable per agent.",
    icon: Shield,
    span: "col-span-1",
    gradient: "from-rose-500/10 to-pink-500/5",
    iconColor: "text-rose-500",
  },
  {
    title: "Hardware-accelerated inference",
    desc: "Automatic GPU routing and model selection. Use any provider — OpenAI, Anthropic, local models — seamlessly.",
    icon: Cpu,
    span: "col-span-1",
    gradient: "from-sky-500/10 to-indigo-500/5",
    iconColor: "text-sky-500",
  },
  {
    title: "AI-powered prompt optimization",
    desc: "Automatic prompt testing, A/B experiments, and optimization suggestions powered by analytics data.",
    icon: Sparkles,
    span: "col-span-1",
    gradient: "from-fuchsia-500/10 to-pink-500/5",
    iconColor: "text-fuchsia-500",
  },
];

/* ── Testimonials ── */
const testimonials = [
  {
    quote:
      "Talmudpedia cut our agent deployment time from weeks to hours. The observability alone justified the switch.",
    name: "Sarah Chen",
    role: "Head of AI, Fintech Corp",
  },
  {
    quote:
      "The graph builder is a game-changer. Our non-technical PMs can now design agent workflows independently.",
    name: "Marcus Webb",
    role: "CTO, DataFlow Labs",
  },
  {
    quote:
      "We manage 40+ agents across 12 tenants. Without Talmudpedia's governance layer, that would be impossible.",
    name: "Priya Sharma",
    role: "VP Engineering, ScaleAI",
  },
  {
    quote:
      "The real-time analytics helped us identify a prompt regression within minutes. Saved us thousands in token spend.",
    name: "James Rodriguez",
    role: "ML Lead, CloudNine",
  },
  {
    quote:
      "Moving from LangChain scripts to Talmudpedia graphs gave us 3x better reliability and full audit trails.",
    name: "Yuki Tanaka",
    role: "Staff Engineer, NexGen",
  },
  {
    quote:
      "Best AI platform we've evaluated. The multi-tenant architecture was exactly what our enterprise clients needed.",
    name: "Elena Kowalski",
    role: "Director of Product, Synthex",
  },
];

export function LandingV9() {
  const [scrolled, setScrolled] = useState(false);
  const [activeTab, setActiveTab] = useState("agents");
  const pageRef = useScrollReveal();

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 40);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const activeFeature = featureTabs.find((t) => t.id === activeTab)!;

  const stat1 = useCountUp(586, 2000);
  const stat2 = useCountUp(94, 2000);
  const stat3 = useCountUp(1560000, 2500);
  const stat4 = useCountUp(120, 1800);

  return (
    <div
      ref={pageRef}
      className="min-h-screen bg-white font-sans overflow-x-hidden selection:bg-black/10"
    >
      <style>{`
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

        @keyframes breathe {
          0%, 100% { transform: scale(1); opacity: 1; }
          50% { transform: scale(1.08); opacity: 0.7; }
        }
        .animate-breathe { animation: breathe 6s ease-in-out infinite; }
        .animate-breathe-slow { animation: breathe 8s ease-in-out infinite; }

        [data-reveal] {
          opacity: 0; transform: translateY(40px);
          transition: opacity 0.8s cubic-bezier(0.16,1,0.3,1), transform 0.8s cubic-bezier(0.16,1,0.3,1);
        }
        [data-reveal].revealed { opacity: 1; transform: translateY(0); }
        [data-reveal="scale"] {
          opacity: 0; transform: scale(0.95);
          transition: opacity 0.9s cubic-bezier(0.16,1,0.3,1), transform 0.9s cubic-bezier(0.16,1,0.3,1);
        }
        [data-reveal="scale"].revealed { opacity: 1; transform: scale(1); }
        [data-reveal="left"] {
          opacity: 0; transform: translateX(-40px);
          transition: opacity 0.8s cubic-bezier(0.16,1,0.3,1), transform 0.8s cubic-bezier(0.16,1,0.3,1);
        }
        [data-reveal="left"].revealed { opacity: 1; transform: translateX(0); }
        [data-reveal="right"] {
          opacity: 0; transform: translateX(40px);
          transition: opacity 0.8s cubic-bezier(0.16,1,0.3,1), transform 0.8s cubic-bezier(0.16,1,0.3,1);
        }
        [data-reveal="right"].revealed { opacity: 1; transform: translateX(0); }

        [data-reveal-delay="1"] { transition-delay: 0.1s; }
        [data-reveal-delay="2"] { transition-delay: 0.2s; }
        [data-reveal-delay="3"] { transition-delay: 0.3s; }
        [data-reveal-delay="4"] { transition-delay: 0.4s; }
        [data-reveal-delay="5"] { transition-delay: 0.5s; }
        [data-reveal-delay="6"] { transition-delay: 0.6s; }

        .screenshot-hover {
          transition: transform 0.5s cubic-bezier(0.16,1,0.3,1), box-shadow 0.5s ease;
        }
        .screenshot-hover:hover {
          transform: translateY(-4px);
          box-shadow: 0 24px 80px -12px rgba(0,0,0,0.12);
        }

        @keyframes marquee {
          0% { transform: translateX(0); }
          100% { transform: translateX(-50%); }
        }
        .animate-marquee { animation: marquee 40s linear infinite; }
        .animate-marquee:hover { animation-play-state: paused; }

        @keyframes float {
          0%, 100% { transform: translateY(0); }
          50% { transform: translateY(-8px); }
        }
        .animate-float { animation: float 4s ease-in-out infinite; }

        @keyframes shimmer {
          0% { background-position: -200% 0; }
          100% { background-position: 200% 0; }
        }
        .animate-shimmer {
          background: linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.08) 50%, transparent 100%);
          background-size: 200% 100%;
          animation: shimmer 3s ease-in-out infinite;
        }

        @keyframes pulse-ring {
          0% { transform: scale(0.8); opacity: 1; }
          100% { transform: scale(2); opacity: 0; }
        }

        .bento-card {
          transition: transform 0.4s cubic-bezier(0.16,1,0.3,1), box-shadow 0.4s ease, border-color 0.4s ease;
        }
        .bento-card:hover {
          transform: translateY(-4px);
          box-shadow: 0 20px 60px -12px rgba(0,0,0,0.08);
          border-color: rgba(0,0,0,0.12);
        }

        .timeline-line {
          background: linear-gradient(to bottom, transparent, #e5e7eb 10%, #e5e7eb 90%, transparent);
        }

        .tab-indicator {
          transition: all 0.4s cubic-bezier(0.16,1,0.3,1);
        }

        .feature-screenshot {
          transition: opacity 0.5s ease, transform 0.5s cubic-bezier(0.16,1,0.3,1);
        }

        @keyframes typing {
          from { width: 0; }
          to { width: 100%; }
        }
        .code-line {
          overflow: hidden;
          white-space: nowrap;
          border-right: 2px solid #22c55e;
          animation: typing 2s steps(40) forwards, blink 0.8s step-end infinite alternate;
        }
        @keyframes blink {
          50% { border-color: transparent; }
        }
      `}</style>

      {/* ══════════════════════════════════════════════════════════════════
          NAV (kept from original)
      ══════════════════════════════════════════════════════════════════ */}
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
            <img src="/kesher.png" alt="Talmudpedia" className="w-7 h-7 rounded-lg" />
            <span className="text-lg font-bold tracking-tight text-black">Talmudpedia</span>
          </Link>
          <div className="flex-1" />
          <div className="hidden md:flex items-center gap-6 text-[13px] font-medium text-[#4b5563]">
            <button className="flex items-center gap-1 hover:text-black transition-colors">
              Platform <ChevronDown className="w-3.5 h-3.5 opacity-60" />
            </button>
            <Link href="#" className="hover:text-black transition-colors">Agents</Link>
            <Link href="#" className="hover:text-black transition-colors">Apps</Link>
            <Link href="#" className="hover:text-black transition-colors">Docs</Link>
            <Link href="#" className="hover:text-black transition-colors">Pricing</Link>
          </div>
          <div className="flex-1" />
          <div className="flex items-center gap-3">
            <Link href="/auth/login" className="hidden sm:block text-[13px] font-medium text-[#4b5563] hover:text-black transition-colors px-3 py-1.5">
              Log in
            </Link>
            <Link href="/auth/login" className="px-4 py-2 bg-black text-white hover:bg-gray-900 text-[13px] font-medium rounded-full transition-colors">
              Start building
            </Link>
          </div>
        </div>
      </nav>

      {/* ══════════════════════════════════════════════════════════════════
          HERO (kept from original)
      ══════════════════════════════════════════════════════════════════ */}
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
            Talmudpedia gives teams a single surface to build agents, manage
            knowledge pipelines, and govern every token in production.
          </p>
          <div className="hero-4 flex flex-col sm:flex-row items-center gap-4 mb-12">
            <Link href="/auth/login" className="px-7 py-3.5 bg-white text-black hover:bg-gray-100 text-[14px] font-medium rounded-full transition-all duration-300 flex items-center gap-2 group shadow-[0_0_30px_rgba(255,255,255,0.1)] hover:shadow-[0_0_40px_rgba(255,255,255,0.2)]">
              Start building
              <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform duration-300" />
            </Link>
            <Link href="/admin/apps" className="px-7 py-3.5 bg-white/10 border border-white/10 hover:bg-white/15 hover:border-white/20 text-white text-[14px] font-medium rounded-full transition-all duration-300 backdrop-blur-md">
              View documentation
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
            <img src={screenshots.dashboard} alt="Talmudpedia Dashboard" className="w-full block rounded-t-[24px]" loading="eager" />
          </div>
        </div>
      </section>

      {/* ══════════════════════════════════════════════════════════════════
          BENTO GRID FEATURES
      ══════════════════════════════════════════════════════════════════ */}
      <section className="relative py-28 md:py-36 px-6 bg-white overflow-hidden">
        <div className="absolute inset-0 bg-[radial-gradient(#e5e7eb_1px,transparent_1px)] bg-[size:24px_24px] opacity-30 [mask-image:radial-gradient(ellipse_70%_50%_at_50%_50%,black,transparent)]" />

        <div className="relative max-w-[1100px] mx-auto">
          <div data-reveal className="text-center mb-16">
            <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full border border-gray-200 bg-gray-50 mb-6">
              <Sparkles className="w-3.5 h-3.5 text-amber-500" />
              <span className="text-[12px] font-semibold text-gray-600 uppercase tracking-[0.12em]">
                Platform Capabilities
              </span>
            </div>
            <h2 className="text-[36px] md:text-[48px] font-medium tracking-tight text-gray-900 mb-5 leading-[1.1]">
              Everything you need to<br className="hidden sm:block" />
              <span className="bg-gradient-to-r from-emerald-600 via-teal-600 to-cyan-600 bg-clip-text text-transparent">
                ship AI at scale
              </span>
            </h2>
            <p className="text-[17px] text-gray-500 max-w-xl mx-auto leading-relaxed">
              A complete toolkit for building, deploying, and governing
              production AI agents — all from one platform.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {bentoItems.map((item, i) => (
              <div
                key={item.title}
                data-reveal
                data-reveal-delay={String(Math.min(i + 1, 6))}
                className={`${item.span} relative rounded-2xl border border-gray-200/80 bg-white p-7 bento-card group overflow-hidden`}
              >
                <div className={`absolute inset-0 bg-gradient-to-br ${item.gradient} opacity-0 group-hover:opacity-100 transition-opacity duration-500`} />
                <div className="relative">
                  <div className={`w-10 h-10 rounded-xl bg-gray-50 border border-gray-100 flex items-center justify-center mb-5 group-hover:scale-110 transition-transform duration-500 ${item.iconColor}`}>
                    <item.icon className="w-5 h-5" />
                  </div>
                  <h3 className="text-[16px] font-semibold text-gray-900 mb-2">
                    {item.title}
                  </h3>
                  <p className="text-[14px] text-gray-500 leading-relaxed">
                    {item.desc}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ══════════════════════════════════════════════════════════════════
          INTERACTIVE FEATURE TABS
      ══════════════════════════════════════════════════════════════════ */}
      <section className="relative py-28 md:py-36 px-6 bg-[#fafafa] overflow-hidden">
        <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-gray-300 to-transparent" />
        <div className="absolute bottom-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-gray-300 to-transparent" />

        <div className="relative max-w-[1100px] mx-auto">
          <div data-reveal className="text-center mb-14">
            <h2 className="text-[36px] md:text-[48px] font-medium tracking-tight text-gray-900 mb-5 leading-[1.1]">
              The complete AI operations stack
            </h2>
            <p className="text-[17px] text-gray-500 max-w-xl mx-auto">
              Every tool you need — agents, builders, analytics, and code artifacts — unified in one surface.
            </p>
          </div>

          {/* Tab buttons */}
          <div data-reveal className="flex justify-center mb-12">
            <div className="inline-flex items-center gap-1 p-1.5 rounded-2xl border border-gray-200 bg-white shadow-sm">
              {featureTabs.map((tab) => {
                const Icon = tab.icon;
                const isActive = activeTab === tab.id;
                return (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id)}
                    className={`flex items-center gap-2 px-5 py-2.5 rounded-xl text-[13px] font-medium transition-all duration-300
                      ${isActive
                        ? "bg-gray-900 text-white shadow-lg"
                        : "text-gray-500 hover:text-gray-900 hover:bg-gray-50"
                      }`}
                  >
                    <Icon className="w-4 h-4" />
                    <span className="hidden sm:inline">{tab.label}</span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Feature content */}
          <div data-reveal="scale" className="relative">
            <div className="grid md:grid-cols-5 gap-8 items-center">
              <div className="md:col-span-2 space-y-5">
                <div
                  className="w-12 h-12 rounded-2xl flex items-center justify-center"
                  style={{ backgroundColor: activeFeature.color + "18" }}
                >
                  <activeFeature.icon
                    className="w-6 h-6"
                    style={{ color: activeFeature.color }}
                  />
                </div>
                <h3 className="text-[28px] md:text-[32px] font-medium tracking-tight text-gray-900 leading-[1.15]">
                  {activeFeature.title}
                </h3>
                <p className="text-[16px] text-gray-500 leading-relaxed">
                  {activeFeature.desc}
                </p>
                <Link
                  href="/admin/agents"
                  className="inline-flex items-center gap-2 text-[14px] font-medium text-gray-900 hover:gap-3 transition-all duration-300 group"
                >
                  Learn more
                  <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
                </Link>
              </div>
              <div className="md:col-span-3 relative">
                <div
                  className="absolute -inset-6 rounded-[2rem] blur-3xl pointer-events-none opacity-40"
                  style={{
                    background: `radial-gradient(ellipse at center, ${activeFeature.color}22, transparent 70%)`,
                  }}
                />
                <div className="relative rounded-2xl overflow-hidden shadow-2xl shadow-black/[0.06] border border-gray-200/80 screenshot-hover">
                  <img
                    src={activeFeature.screenshot}
                    alt={activeFeature.label}
                    className="w-full block feature-screenshot"
                    loading="lazy"
                  />
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ══════════════════════════════════════════════════════════════════
          HOW IT WORKS — ANIMATED TIMELINE
      ══════════════════════════════════════════════════════════════════ */}
      <section className="relative py-28 md:py-36 px-6 bg-white overflow-hidden">
        <div className="relative max-w-[900px] mx-auto">
          <div data-reveal className="text-center mb-20">
            <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full border border-gray-200 bg-gray-50 mb-6">
              <Workflow className="w-3.5 h-3.5 text-purple-500" />
              <span className="text-[12px] font-semibold text-gray-600 uppercase tracking-[0.12em]">
                How it works
              </span>
            </div>
            <h2 className="text-[36px] md:text-[48px] font-medium tracking-tight text-gray-900 mb-5 leading-[1.1]">
              From idea to production<br className="hidden sm:block" />in four steps
            </h2>
          </div>

          <div className="relative">
            {/* Vertical line */}
            <div className="absolute left-8 md:left-1/2 md:-translate-x-px top-0 bottom-0 w-px timeline-line hidden md:block" />

            <div className="space-y-12 md:space-y-20">
              {timelineSteps.map((step, i) => {
                const Icon = step.icon;
                const isEven = i % 2 === 0;
                return (
                  <div
                    key={step.num}
                    data-reveal={isEven ? "left" : "right"}
                    className={`relative flex items-start gap-8 md:gap-0 ${
                      isEven ? "md:flex-row" : "md:flex-row-reverse"
                    }`}
                  >
                    {/* Content card */}
                    <div className={`md:w-[calc(50%-40px)] ${isEven ? "md:pr-0" : "md:pl-0"}`}>
                      <div className="relative rounded-2xl border border-gray-200/80 bg-white p-8 shadow-sm hover:shadow-md transition-shadow duration-500">
                        <div className="absolute -inset-px rounded-2xl bg-gradient-to-br from-gray-100 via-transparent to-transparent opacity-0 hover:opacity-100 transition-opacity duration-500 pointer-events-none" />
                        <div className="relative">
                          <div className="flex items-center gap-4 mb-4">
                            <span
                              className="text-[36px] font-bold tracking-tight leading-none"
                              style={{ color: step.color + "30" }}
                            >
                              {step.num}
                            </span>
                            <div
                              className="w-10 h-10 rounded-xl flex items-center justify-center"
                              style={{ backgroundColor: step.color + "15" }}
                            >
                              <Icon className="w-5 h-5" style={{ color: step.color }} />
                            </div>
                          </div>
                          <h3 className="text-[20px] font-semibold text-gray-900 mb-2">
                            {step.title}
                          </h3>
                          <p className="text-[15px] text-gray-500 leading-relaxed">
                            {step.desc}
                          </p>
                        </div>
                      </div>
                    </div>

                    {/* Center dot (desktop) */}
                    <div className="hidden md:flex absolute left-1/2 -translate-x-1/2 top-8 w-8 h-8 rounded-full border-4 border-white bg-white shadow-md items-center justify-center z-10">
                      <div
                        className="w-3 h-3 rounded-full"
                        style={{ backgroundColor: step.color }}
                      />
                    </div>

                    {/* Empty spacer */}
                    <div className="hidden md:block md:w-[calc(50%-40px)]" />
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </section>

      {/* ══════════════════════════════════════════════════════════════════
          ANIMATED COUNTERS — DARK SECTION
      ══════════════════════════════════════════════════════════════════ */}
      <section className="relative py-24 md:py-32 px-6 bg-[#0a0a0a] overflow-hidden">
        <div className="absolute inset-0 bg-[linear-gradient(to_right,#ffffff05_1px,transparent_1px),linear-gradient(to_bottom,#ffffff05_1px,transparent_1px)] bg-[size:48px_48px] [mask-image:radial-gradient(ellipse_50%_50%_at_50%_50%,black,transparent)]" />
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[500px] bg-emerald-500/[0.03] blur-[160px] rounded-full pointer-events-none animate-breathe" />

        <div className="relative max-w-[1100px] mx-auto">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-8 md:gap-4">
            {[
              { ref: stat1.ref, value: stat1.count.toLocaleString(), suffix: "", label: "Agent runs this month", color: "#22c55e" },
              { ref: stat2.ref, value: stat2.count.toString(), suffix: ".4%", label: "Success rate across agents", color: "#a855f7" },
              { ref: stat3.ref, value: (stat3.count / 1000000).toFixed(2), suffix: "M", label: "Tokens governed & tracked", color: "#f59e0b" },
              { ref: stat4.ref, value: "<" + stat4.count, suffix: "ms", label: "Median response latency", color: "#3b82f6" },
            ].map((m) => (
              <div key={m.label} ref={m.ref} className="text-center group">
                <div className="relative inline-block">
                  <div
                    className="text-[44px] md:text-[56px] font-bold tracking-tight leading-none text-white"
                  >
                    {m.value}
                    <span style={{ color: m.color }}>{m.suffix}</span>
                  </div>
                  <div
                    className="absolute -bottom-1 left-0 right-0 h-px opacity-40"
                    style={{
                      background: `linear-gradient(90deg, transparent, ${m.color}60, transparent)`,
                    }}
                  />
                </div>
                <div className="text-[13px] text-white/40 mt-4 font-medium">
                  {m.label}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ══════════════════════════════════════════════════════════════════
          APPS & PROMPTS — GLASS CARDS
      ══════════════════════════════════════════════════════════════════ */}
      <section className="relative py-28 md:py-36 px-6 bg-white overflow-hidden">
        <div className="absolute inset-0 bg-[radial-gradient(#e5e7eb_1px,transparent_1px)] bg-[size:32px_32px] opacity-25 [mask-image:linear-gradient(to_bottom,transparent,black_20%,black_80%,transparent)]" />

        <div className="relative max-w-[1100px] mx-auto">
          <div data-reveal className="text-center mb-16">
            <h2 className="text-[36px] md:text-[48px] font-medium tracking-tight text-gray-900 mb-5 leading-[1.1]">
              Apps and prompts,<br />
              <span className="bg-gradient-to-r from-purple-600 via-violet-600 to-indigo-600 bg-clip-text text-transparent">
                all in one place
              </span>
            </h2>
            <p className="text-[17px] text-gray-500 max-w-xl mx-auto">
              Publish agent-backed applications and maintain a shared prompt
              library across your organization.
            </p>
          </div>

          <div className="grid md:grid-cols-2 gap-6">
            {[
              {
                src: screenshots.apps,
                alt: "Published Apps",
                title: "Published Apps",
                desc: "Deploy and manage agent-powered applications with one click",
                gradient: "from-emerald-500/8 via-teal-500/4 to-transparent",
                borderHover: "hover:border-emerald-200",
              },
              {
                src: screenshots.prompts,
                alt: "Prompt Library",
                title: "Prompt Library",
                desc: "Shared, versioned prompts with A/B testing built in",
                gradient: "from-purple-500/8 via-violet-500/4 to-transparent",
                borderHover: "hover:border-purple-200",
              },
            ].map((card, i) => (
              <div
                key={card.title}
                data-reveal
                data-reveal-delay={String(i + 1)}
                className={`relative group rounded-3xl border border-gray-200/80 bg-white overflow-hidden screenshot-hover ${card.borderHover} transition-all duration-500`}
              >
                <div className={`absolute inset-0 bg-gradient-to-br ${card.gradient} opacity-0 group-hover:opacity-100 transition-opacity duration-700`} />
                <div className="relative p-5 pb-0">
                  <div className="rounded-xl overflow-hidden border border-gray-100">
                    <img src={card.src} alt={card.alt} className="w-full block" loading="lazy" />
                  </div>
                </div>
                <div className="relative p-6 pt-5">
                  <h3 className="text-[18px] font-semibold text-gray-900 mb-1">
                    {card.title}
                  </h3>
                  <p className="text-[14px] text-gray-500">{card.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ══════════════════════════════════════════════════════════════════
          MARQUEE TESTIMONIALS
      ══════════════════════════════════════════════════════════════════ */}
      <section className="relative py-20 md:py-24 bg-[#fafafa] overflow-hidden border-y border-gray-200/60">
        <div data-reveal className="text-center mb-14 px-6">
          <h2 className="text-[28px] md:text-[36px] font-medium tracking-tight text-gray-900">
            Loved by AI teams everywhere
          </h2>
        </div>

        <div className="relative">
          {/* Left/right fades */}
          <div className="absolute top-0 left-0 w-20 md:w-40 h-full bg-gradient-to-r from-[#fafafa] to-transparent z-10 pointer-events-none" />
          <div className="absolute top-0 right-0 w-20 md:w-40 h-full bg-gradient-to-l from-[#fafafa] to-transparent z-10 pointer-events-none" />

          <div className="flex animate-marquee" style={{ width: "max-content" }}>
            {[...testimonials, ...testimonials].map((t, i) => (
              <div
                key={`${t.name}-${i}`}
                className="flex-shrink-0 w-[360px] mx-3 p-6 rounded-2xl border border-gray-200/80 bg-white shadow-sm hover:shadow-md transition-shadow duration-300"
              >
                <p className="text-[14px] text-gray-600 leading-relaxed mb-5 italic">
                  &ldquo;{t.quote}&rdquo;
                </p>
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 rounded-full bg-gradient-to-br from-gray-200 to-gray-300 flex items-center justify-center text-[13px] font-bold text-gray-600">
                    {t.name.charAt(0)}
                  </div>
                  <div>
                    <div className="text-[13px] font-semibold text-gray-900">{t.name}</div>
                    <div className="text-[12px] text-gray-400">{t.role}</div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ══════════════════════════════════════════════════════════════════
          API / CODE SECTION
      ══════════════════════════════════════════════════════════════════ */}
      <section className="relative py-28 md:py-36 px-6 bg-white overflow-hidden">
        <div className="relative max-w-[1100px] mx-auto">
          <div className="grid md:grid-cols-2 gap-12 md:gap-16 items-center">
            <div data-reveal="left">
              <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full border border-gray-200 bg-gray-50 mb-6">
                <Terminal className="w-3.5 h-3.5 text-emerald-500" />
                <span className="text-[12px] font-semibold text-gray-600 uppercase tracking-[0.12em]">
                  Developer-first
                </span>
              </div>
              <h2 className="text-[32px] md:text-[40px] font-medium tracking-tight text-gray-900 leading-[1.1] mb-5">
                Built for developers<br />who ship fast
              </h2>
              <p className="text-[16px] text-gray-500 leading-relaxed mb-8">
                Full REST API, Python and TypeScript SDKs, webhooks, and CLI
                tools. Integrate Talmudpedia into your existing workflow in
                minutes, not weeks.
              </p>
              <div className="flex flex-wrap gap-3">
                {["REST API", "Python SDK", "TypeScript SDK", "Webhooks", "CLI"].map(
                  (tag) => (
                    <span
                      key={tag}
                      className="px-3 py-1.5 rounded-lg border border-gray-200 bg-gray-50 text-[12px] font-medium text-gray-600"
                    >
                      {tag}
                    </span>
                  )
                )}
              </div>
            </div>
            <div data-reveal="right">
              <div className="rounded-2xl overflow-hidden border border-gray-800 bg-[#0a0a0a] shadow-2xl shadow-black/20">
                {/* Window chrome */}
                <div className="flex items-center gap-2 px-4 py-3 border-b border-white/10">
                  <div className="w-3 h-3 rounded-full bg-[#ff5f57]" />
                  <div className="w-3 h-3 rounded-full bg-[#ffbd2e]" />
                  <div className="w-3 h-3 rounded-full bg-[#28c840]" />
                  <span className="ml-3 text-[11px] text-white/30 font-mono">
                    quickstart.py
                  </span>
                </div>
                <div className="p-6 font-mono text-[13px] leading-[1.8] overflow-x-auto">
                  <div className="text-gray-500"># Initialize the Talmudpedia client</div>
                  <div>
                    <span className="text-purple-400">from</span>{" "}
                    <span className="text-emerald-400">talmudpedia</span>{" "}
                    <span className="text-purple-400">import</span>{" "}
                    <span className="text-white">Client</span>
                  </div>
                  <div className="mt-2">
                    <span className="text-white">client</span>{" "}
                    <span className="text-gray-400">=</span>{" "}
                    <span className="text-emerald-400">Client</span>
                    <span className="text-gray-400">(</span>
                    <span className="text-amber-300">api_key</span>
                    <span className="text-gray-400">=</span>
                    <span className="text-emerald-300">&quot;sk_...&quot;</span>
                    <span className="text-gray-400">)</span>
                  </div>
                  <div className="mt-4 text-gray-500"># Run an agent</div>
                  <div>
                    <span className="text-white">result</span>{" "}
                    <span className="text-gray-400">=</span>{" "}
                    <span className="text-white">client</span>
                    <span className="text-gray-400">.</span>
                    <span className="text-blue-400">agents</span>
                    <span className="text-gray-400">.</span>
                    <span className="text-blue-400">run</span>
                    <span className="text-gray-400">(</span>
                  </div>
                  <div className="pl-4">
                    <span className="text-amber-300">agent_id</span>
                    <span className="text-gray-400">=</span>
                    <span className="text-emerald-300">&quot;ag_invoice_processor&quot;</span>
                    <span className="text-gray-400">,</span>
                  </div>
                  <div className="pl-4">
                    <span className="text-amber-300">input</span>
                    <span className="text-gray-400">=</span>
                    <span className="text-emerald-300">&quot;Process Q4 invoices&quot;</span>
                    <span className="text-gray-400">,</span>
                  </div>
                  <div className="pl-4">
                    <span className="text-amber-300">stream</span>
                    <span className="text-gray-400">=</span>
                    <span className="text-purple-400">True</span>
                  </div>
                  <div>
                    <span className="text-gray-400">)</span>
                  </div>
                  <div className="mt-4 text-gray-500"># Stream the response</div>
                  <div>
                    <span className="text-purple-400">for</span>{" "}
                    <span className="text-white">chunk</span>{" "}
                    <span className="text-purple-400">in</span>{" "}
                    <span className="text-white">result</span>
                    <span className="text-gray-400">:</span>
                  </div>
                  <div className="pl-4">
                    <span className="text-blue-400">print</span>
                    <span className="text-gray-400">(</span>
                    <span className="text-white">chunk</span>
                    <span className="text-gray-400">.</span>
                    <span className="text-blue-400">text</span>
                    <span className="text-gray-400">,</span>{" "}
                    <span className="text-amber-300">end</span>
                    <span className="text-gray-400">=</span>
                    <span className="text-emerald-300">&quot;&quot;</span>
                    <span className="text-gray-400">)</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ══════════════════════════════════════════════════════════════════
          GRADIENT CTA
      ══════════════════════════════════════════════════════════════════ */}
      <section className="relative py-28 md:py-36 px-6 overflow-hidden">
        <div className="absolute inset-0 bg-[#0a0a0a]" />
        <div className="absolute inset-0 bg-gradient-to-br from-emerald-900/30 via-transparent to-purple-900/20" />
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-emerald-500/[0.06] blur-[180px] rounded-full pointer-events-none animate-breathe-slow" />
        <div className="absolute inset-0 bg-[linear-gradient(to_right,#ffffff05_1px,transparent_1px),linear-gradient(to_bottom,#ffffff05_1px,transparent_1px)] bg-[size:48px_48px] [mask-image:radial-gradient(ellipse_40%_40%_at_50%_50%,black,transparent)]" />

        <div data-reveal className="relative max-w-3xl mx-auto text-center z-10">
          <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full border border-white/10 bg-white/[0.04] backdrop-blur-md mb-8">
            <span className="flex h-2 w-2 rounded-full bg-[#22c55e] animate-pulse" />
            <span className="text-[12px] font-medium tracking-wide text-white/60 uppercase">
              Ready to deploy
            </span>
          </div>
          <h2 className="text-[40px] md:text-[56px] font-medium tracking-tight text-white mb-6 leading-[1.05]">
            Start building<br />with Talmudpedia
          </h2>
          <p className="text-[17px] text-white/50 max-w-lg mx-auto mb-10 leading-relaxed">
            Deploy your first agent in minutes. No infrastructure to manage, no
            vendor lock-in, full visibility into every token.
          </p>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <Link
              href="/auth/login"
              className="px-8 py-4 bg-white text-black hover:bg-gray-100 text-[14px] font-medium rounded-full transition-all duration-300 flex items-center gap-2 group shadow-[0_0_40px_rgba(255,255,255,0.1)] hover:shadow-[0_0_60px_rgba(255,255,255,0.2)]"
            >
              Start building — it&apos;s free
              <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform duration-300" />
            </Link>
            <Link
              href="/admin/apps"
              className="px-8 py-4 bg-white/10 border border-white/10 hover:bg-white/15 hover:border-white/20 text-white text-[14px] font-medium rounded-full transition-all duration-300 backdrop-blur-md"
            >
              Talk to sales
            </Link>
          </div>
        </div>
      </section>

      {/* ══════════════════════════════════════════════════════════════════
          MULTI-COLUMN FOOTER
      ══════════════════════════════════════════════════════════════════ */}
      <footer className="bg-white border-t border-gray-100 py-16 px-6">
        <div className="max-w-[1100px] mx-auto">
          <div className="grid grid-cols-2 md:grid-cols-5 gap-10 mb-14">
            {/* Brand */}
            <div className="col-span-2 md:col-span-1">
              <div className="flex items-center gap-2.5 mb-4">
                <img src="/kesher.png" alt="Talmudpedia" className="w-7 h-7 rounded-lg" />
                <span className="text-[15px] font-bold tracking-tight text-gray-900">
                  Talmudpedia
                </span>
              </div>
              <p className="text-[13px] text-gray-400 leading-relaxed max-w-[200px]">
                The multi-tenant AI operations platform built for production teams.
              </p>
            </div>

            {/* Links */}
            {[
              {
                title: "Product",
                links: ["Agents", "Graph Builder", "Analytics", "Code Artifacts", "Pricing"],
              },
              {
                title: "Developers",
                links: ["Documentation", "API Reference", "SDKs", "Changelog", "Status"],
              },
              {
                title: "Company",
                links: ["About", "Blog", "Careers", "Contact", "Press"],
              },
              {
                title: "Legal",
                links: ["Privacy", "Terms", "Security", "GDPR", "SOC 2"],
              },
            ].map((group) => (
              <div key={group.title}>
                <div className="text-[12px] font-semibold text-gray-900 uppercase tracking-[0.1em] mb-4">
                  {group.title}
                </div>
                <ul className="space-y-2.5">
                  {group.links.map((link) => (
                    <li key={link}>
                      <Link
                        href="#"
                        className="text-[13px] text-gray-400 hover:text-gray-900 transition-colors duration-200"
                      >
                        {link}
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>

          {/* Bottom */}
          <div className="pt-8 border-t border-gray-100 flex flex-col sm:flex-row items-center justify-between gap-4">
            <span className="text-[12px] text-gray-400">
              © 2026 Talmudpedia. All rights reserved.
            </span>
            <div className="flex items-center gap-5">
              {["Twitter", "GitHub", "LinkedIn", "Discord"].map((social) => (
                <Link
                  key={social}
                  href="#"
                  className="text-[12px] text-gray-400 hover:text-gray-900 transition-colors duration-200"
                >
                  {social}
                </Link>
              ))}
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}
