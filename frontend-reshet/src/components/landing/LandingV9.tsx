"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { AnimatePresence, motion, useMotionTemplate, useMotionValueEvent, useReducedMotion, useScroll, useTransform } from "motion/react";
import { ArrowRight, ChevronDown } from "lucide-react";

type HeroMetrics = {
  logoStartTop: number;
  logoStartSize: number;
  topArcHeight: number;
  seamY: number;
  apexYOpen: number;
  sceneHeight: string;
  logoFinalTop: number;
  logoFinalRight: number;
  logoFinalSize: number;
};

const MOBILE_METRICS: HeroMetrics = {
  logoStartTop: 850,
  logoStartSize: 228,
  topArcHeight: 140,
  seamY: 590,
  apexYOpen: 390,
  sceneHeight: "205vh",
  logoFinalTop: 92,
  logoFinalRight: 20,
  logoFinalSize: 78,
};

const DESKTOP_METRICS: HeroMetrics = {
  logoStartTop: 710,
  logoStartSize: 560,
  topArcHeight: 108,
  seamY: 560,
  apexYOpen: 320,
  sceneHeight: "220vh",
  logoFinalTop: 96,
  logoFinalRight: 28,
  logoFinalSize: 88,
};

const PLATFORM_DOMAINS = [
  {
    title: "Agent Graphs",
    eyebrow: "Execution",
    heading: "Design and operate graph-based agent systems without splitting authoring from runtime.",
    body: "Move from prompt chains to explicit execution graphs, tool orchestration, and governed runtime behavior in one surface.",
    points: ["Graph authoring", "Tool contracts", "Runtime execution", "Trace visibility"],
  },
  {
    title: "Knowledge",
    eyebrow: "Retrieval",
    heading: "Attach structured knowledge pipelines directly to the platform that serves production agents.",
    body: "Keep ingestion, retrieval, source management, and operator-level control in the same operating layer as your deployed agents.",
    points: ["Source pipelines", "Operator tuning", "Index governance", "Answer grounding"],
  },
  {
    title: "Governance",
    eyebrow: "Control",
    heading: "Track cost, permissions, and model behavior with explicit platform rules instead of ad-hoc conventions.",
    body: "Make runtime budgets, model policy, resource controls, and operator boundaries first-class platform primitives.",
    points: ["Quota policy", "Scope control", "Model routing", "Usage accounting"],
  },
  {
    title: "Deployments",
    eyebrow: "Runtime",
    heading: "Move from local iteration to deployed runtime surfaces without losing visibility or control.",
    body: "Ship hosted experiences, embedded runtimes, and managed app surfaces from the same platform backbone.",
    points: ["Hosted apps", "Embedded runtime", "Preview flow", "Release controls"],
  },
] as const;

export function LandingV9() {
  const [scrolled, setScrolled] = useState(false);
  const [isMobile, setIsMobile] = useState(false);
  const [viewportWidth, setViewportWidth] = useState(1440);
  const [activeDomainIndex, setActiveDomainIndex] = useState(0);
  const [domainsScenePhase, setDomainsScenePhase] = useState<"before" | "active" | "after">("before");
  const heroSceneRef = useRef<HTMLElement | null>(null);
  const domainsSceneRef = useRef<HTMLElement | null>(null);
  const prefersReducedMotion = useReducedMotion();

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 40);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    const updateDomainsScenePhase = () => {
      const rect = domainsSceneRef.current?.getBoundingClientRect();
      if (!rect) return;

      if (rect.top > 0) {
        setDomainsScenePhase("before");
        return;
      }

      if (rect.bottom < window.innerHeight) {
        setDomainsScenePhase("after");
        return;
      }

      setDomainsScenePhase("active");
    };

    updateDomainsScenePhase();
    window.addEventListener("scroll", updateDomainsScenePhase, { passive: true });
    window.addEventListener("resize", updateDomainsScenePhase, { passive: true });

    return () => {
      window.removeEventListener("scroll", updateDomainsScenePhase);
      window.removeEventListener("resize", updateDomainsScenePhase);
    };
  }, []);

  useEffect(() => {
    const media = window.matchMedia("(max-width: 767px)");
    const update = () => setIsMobile(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    const update = () => setViewportWidth(window.innerWidth);
    update();
    window.addEventListener("resize", update, { passive: true });
    return () => window.removeEventListener("resize", update);
  }, []);

  const metrics = isMobile ? MOBILE_METRICS : DESKTOP_METRICS;

  const { scrollYProgress } = useScroll({
    target: heroSceneRef,
    offset: ["start start", "end end"],
  });
  const { scrollYProgress: domainsScrollProgress } = useScroll({
    target: domainsSceneRef,
    offset: ["start start", "end end"],
  });

  const rawProgress = useTransform(scrollYProgress, (value) => {
    if (prefersReducedMotion) return 0;
    if (value <= 0.31) return 0;
    if (value >= 0.92) return 1;
    return (value - 0.31) / 0.61;
  });

  const logoLiftProgress = useTransform(scrollYProgress, (value) => {
    if (prefersReducedMotion) return 0;
    if (value <= 0.015) return 0;
    if (value >= 0.34) return 1;
    return (value - 0.015) / 0.325;
  });

  const logoTravelProgress = useTransform(scrollYProgress, (value) => {
    if (prefersReducedMotion) return 0;
    if (value <= 0.48) return 0;
    if (value >= 1) return 1;
    return (value - 0.48) / 0.52;
  });

  const notchApexY = useTransform(rawProgress, [0, 1], [metrics.apexYOpen, metrics.seamY]);
  const leftInnerX = useTransform(rawProgress, [0, 1], [isMobile ? 475 : 475, 600]);
  const rightInnerX = useTransform(rawProgress, [0, 1], [isMobile ? 965 : 965, 840]);
  const logoRestTop = useTransform(logoLiftProgress, [0, 1], [metrics.logoStartTop, metrics.logoStartTop - (isMobile ? 300 : 380)]);
  const logoTop = useTransform<number, number>([logoRestTop, logoTravelProgress], ([restTop, travel]) => {
    const finalTop = metrics.logoFinalTop;
    return restTop + (finalTop - restTop) * travel;
  });
  const logoSize = useTransform(logoTravelProgress, [0, 1], [metrics.logoStartSize, metrics.logoFinalSize]);
  const logoLeft = useTransform(
    logoTravelProgress,
    [0, 1],
    [viewportWidth / 2, viewportWidth - metrics.logoFinalRight - metrics.logoFinalSize / 2],
  );
  const logoX = useTransform(logoSize, (value) => -value / 2);
  const logoRotate = useTransform(logoTravelProgress, [0, 1], [0, 420]);
  const logoOpacity = useTransform(rawProgress, [0, 0.12, 1], [1, 1, 1]);
  const domainStops = PLATFORM_DOMAINS.map((_, index) => index / (PLATFORM_DOMAINS.length - 1));
  const domainLogoTopPositions = PLATFORM_DOMAINS.map((_, index) =>
    metrics.logoFinalTop + index * (isMobile ? 64 : 88),
  );
  const domainLogoTop = useTransform(domainsScrollProgress, domainStops, domainLogoTopPositions);
  const domainLogoOpacity = useTransform(domainsScrollProgress, [0, 0.03, 1], [0, 1, 1]);
  const heroFixedLogoOpacity = useTransform<number, number>(
    [logoOpacity, domainLogoOpacity],
    ([heroOpacity, domainOpacity]) => heroOpacity * (1 - domainOpacity),
  );

  useMotionValueEvent(domainsScrollProgress, "change", (value) => {
    const nextIndex = Math.min(
      PLATFORM_DOMAINS.length - 1,
      Math.max(0, Math.round(value * (PLATFORM_DOMAINS.length - 1))),
    );
    setActiveDomainIndex(nextIndex);
  });

  const bottomNotchPath = useMotionTemplate`M0 ${metrics.seamY}
                   C 80 ${metrics.seamY}, 170 ${metrics.seamY}, 250 ${metrics.seamY}
                   C 420 ${metrics.seamY}, ${leftInnerX} ${notchApexY}, 720 ${notchApexY}
                   C ${rightInnerX} ${notchApexY}, 1020 ${metrics.seamY}, 1190 ${metrics.seamY}
                   C 1270 ${metrics.seamY}, 1360 ${metrics.seamY}, 1440 ${metrics.seamY}
                   L1440 560
                   L0 560
                   Z`;

  return (
    <div className="min-h-screen bg-white font-sans overflow-x-hidden selection:bg-black/10">
      <style>{`
        html { scroll-behavior: smooth; }
        @keyframes heroFadeUp {
          from { opacity: 0; transform: translateY(28px); }
          to { opacity: 1; transform: translateY(0); }
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
        @keyframes breathe {
          0%, 100% { transform: scale(1); opacity: 1; }
          50% { transform: scale(1.08); opacity: 0.7; }
        }
        .animate-breathe { animation: breathe 6s ease-in-out infinite; }
        .animate-breathe-slow { animation: breathe 8s ease-in-out infinite; }
      `}</style>

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
            <Image src="/kesher.png" alt="AGENTS24" width={28} height={28} className="h-7 w-7 rounded-lg" />
            <span className="text-lg font-bold tracking-tight text-black">AGENTS24</span>
          </Link>
          <div className="flex-1" />
          <div className="hidden md:flex items-center gap-6 text-[13px] font-medium text-[#4b5563]">
            <Link href="#platform" className="flex items-center gap-1 hover:text-black transition-colors">
              Platform <ChevronDown className="w-3.5 h-3.5 opacity-60" />
            </Link>
            <Link href="#platform" className="hover:text-black transition-colors">Structure</Link>
            <Link href="#platform" className="hover:text-black transition-colors">Governance</Link>
            <Link href="#platform" className="hover:text-black transition-colors">Deploy</Link>
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

      <motion.div
        className="fixed z-40 pointer-events-none"
        style={{
          top: logoTop,
          left: logoLeft,
          width: logoSize,
          height: logoSize,
          x: logoX,
          rotate: logoRotate,
          opacity: heroFixedLogoOpacity,
        }}
      >
        <Image src="/kesher.png" alt="AGENTS24" width={560} height={560} className="h-full w-full object-contain" priority />
      </motion.div>

      <motion.div
        className="fixed z-40 pointer-events-none"
        style={{
          top: domainLogoTop,
          left: viewportWidth - metrics.logoFinalRight - metrics.logoFinalSize / 2,
          width: metrics.logoFinalSize,
          height: metrics.logoFinalSize,
          x: -metrics.logoFinalSize / 2,
          opacity: domainLogoOpacity,
        }}
      >
        <Image src="/kesher.png" alt="AGENTS24" width={88} height={88} className="h-full w-full object-contain" />
      </motion.div>

      <section
        ref={heroSceneRef}
        className="relative"
        style={{ height: metrics.sceneHeight }}
      >
        <div className="sticky top-0 h-screen overflow-hidden bg-[#0a0a0a]">
          <div className="absolute top-0 left-0 right-0 z-10 pointer-events-none">
            <svg viewBox="0 0 1440 160" fill="none" className="h-[140px] w-full md:h-[clamp(88px,14vw,140px)]" preserveAspectRatio="none">
              <path d="M0 0H1440V54C1440 54 1200 108 720 108C240 108 0 54 0 54V0Z" fill="white" />
            </svg>
          </div>

          <div className="absolute inset-0 bg-[linear-gradient(to_right,#ffffff08_1px,transparent_1px),linear-gradient(to_bottom,#ffffff08_1px,transparent_1px)] bg-[size:48px_48px] [mask-image:radial-gradient(ellipse_80%_50%_at_50%_30%,black_20%,transparent_100%)]" />
          <div className="absolute top-[15%] left-1/2 -translate-x-1/2 h-[400px] w-[700px] rounded-full bg-white/[0.03] blur-[140px] pointer-events-none animate-breathe" />
          <div className="absolute top-[45%] left-[20%] h-[300px] w-[300px] rounded-full bg-emerald-500/[0.02] blur-[100px] pointer-events-none animate-breathe-slow" />
          <div className="absolute top-[30%] right-[15%] h-[250px] w-[250px] rounded-full bg-blue-500/[0.02] blur-[100px] pointer-events-none animate-breathe" />

          <div className="relative z-20 flex h-full flex-col items-center px-6 pt-36 pb-[24rem] md:pb-[38rem] text-center">
            <div className="hero-1 mb-8 inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.04] px-3.5 py-1.5 backdrop-blur-md">
              <span className="flex h-2 w-2 rounded-full bg-[#22c55e] animate-pulse" />
              <span className="text-[12px] font-medium tracking-wide text-white/70 uppercase">
                Multi-tenant AI Platform
              </span>
            </div>
            <h1 className="hero-2 mb-6 text-[48px] font-medium leading-[1.05] tracking-tight text-white sm:text-[56px] md:text-[68px]">
              Your AI operations,
              <br />
              one dashboard.
            </h1>
            <p className="hero-3 mb-10 max-w-2xl text-[17px] leading-relaxed text-[#a1a1aa] md:text-[18px]">
              AGENTS24 gives teams a single surface to build agents, manage knowledge
              pipelines, and govern every token in production.
            </p>
            <div className="hero-4 mb-12 flex flex-col items-center gap-4 sm:flex-row">
              <Link href="/auth/signup" className="group flex items-center gap-2 rounded-full bg-white px-7 py-3.5 text-[14px] font-medium text-black transition-all duration-300 hover:bg-gray-100 hover:shadow-[0_0_40px_rgba(255,255,255,0.2)] shadow-[0_0_30px_rgba(255,255,255,0.1)]">
                Start building
                <ArrowRight className="h-4 w-4 transition-transform duration-300 group-hover:translate-x-1" />
              </Link>
              <Link href="#platform" className="rounded-full border border-white/10 bg-white/10 px-7 py-3.5 text-[14px] font-medium text-white backdrop-blur-md transition-all duration-300 hover:border-white/20 hover:bg-white/15">
                View platform
              </Link>
            </div>
          </div>

          <div className="absolute inset-x-0 bottom-0 z-20 pointer-events-none overflow-visible">
            <div className="relative h-[220px] md:h-[clamp(360px,42vw,560px)]">
              <svg
                viewBox="0 0 1440 560"
                preserveAspectRatio="none"
                className="absolute inset-x-0 bottom-[-2px] h-[calc(100%+4px)] w-full"
                aria-hidden="true"
              >
                <motion.path d={bottomNotchPath} fill="white" />
              </svg>
            </div>
          </div>
        </div>
      </section>

      <main className="relative -mt-[54vh] bg-white md:-mt-[60vh]">
        <section
          ref={domainsSceneRef}
          id="platform"
          className="relative"
          style={{ height: isMobile ? "260vh" : "320vh" }}
        >
          <div
            className={`h-screen overflow-visible bg-white ${
              domainsScenePhase === "active"
                ? "fixed inset-x-0 top-0 z-20"
                : "absolute inset-x-0 z-20"
            } ${domainsScenePhase === "before" ? "top-0" : ""} ${domainsScenePhase === "after" ? "bottom-0" : ""}`}
          >
            <div className="mx-auto grid h-full max-w-[1480px] gap-10 px-6 md:grid-cols-[minmax(0,1.15fr)_360px] md:gap-16">
              <div className="relative flex min-h-0 items-center py-24 md:py-28">
                <AnimatePresence mode="wait">
                  <motion.div
                    key={PLATFORM_DOMAINS[activeDomainIndex].title}
                    initial={{ opacity: 0, y: 24 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -24 }}
                    transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
                    className="w-full rounded-[34px] border border-[#0a0a0a]/8 bg-[#f6f3ee] p-8 shadow-[0_30px_80px_-45px_rgba(10,10,10,0.28)] md:p-12"
                  >
                    <p className="mb-4 text-xs font-semibold uppercase tracking-[0.28em] text-[#0a0a0a]/45">
                      {PLATFORM_DOMAINS[activeDomainIndex].eyebrow}
                    </p>
                    <h2 className="max-w-3xl text-[34px] font-medium leading-[0.98] tracking-tight text-[#0a0a0a] md:text-[58px]">
                      {PLATFORM_DOMAINS[activeDomainIndex].heading}
                    </h2>
                    <p className="mt-6 max-w-2xl text-[17px] leading-8 text-[#0a0a0a]/65 md:text-[19px]">
                      {PLATFORM_DOMAINS[activeDomainIndex].body}
                    </p>
                    <div className="mt-10 grid gap-3 sm:grid-cols-2">
                      {PLATFORM_DOMAINS[activeDomainIndex].points.map((point) => (
                        <div key={point} className="rounded-[22px] border border-[#0a0a0a]/7 bg-white/70 px-5 py-4 text-[15px] font-medium text-[#0a0a0a]/78">
                          {point}
                        </div>
                      ))}
                    </div>
                  </motion.div>
                </AnimatePresence>
              </div>

              <div className="relative hidden self-start md:block">
                <div className="relative">
                  {PLATFORM_DOMAINS.map((domain, index) => (
                    <div
                      key={domain.title}
                      className="absolute right-[120px] w-[200px] text-right"
                      style={{ top: `${domainLogoTopPositions[index] + metrics.logoFinalSize / 2 - 14}px` }}
                    >
                      <p className={`text-[19px] font-medium tracking-tight transition-colors duration-300 ${
                        index === activeDomainIndex ? "text-[#0a0a0a]" : "text-[#0a0a0a]/28"
                      }`}>
                        {domain.title}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </section>
      </main>

      <footer className="bg-white border-t border-gray-100">
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
              { links: [{ label: "Product", href: "#platform" }, { label: "Structure", href: "#platform" }, { label: "Governance", href: "#platform" }, { label: "Deploy", href: "#platform" }] },
              { links: [{ label: "Sign Up", href: "/auth/signup" }, { label: "Log In", href: "/auth/login" }] },
              { links: [{ label: "Agents", href: "#platform" }, { label: "Knowledge", href: "#platform" }, { label: "Controls", href: "#platform" }] },
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

        <div className="px-6 pb-6">
          <h2
            className="text-[18vw] md:text-[14vw] font-black tracking-tighter text-gray-900 leading-[0.85] select-none"
            style={{ fontFamily: "system-ui, -apple-system, sans-serif" }}
          >
            AGENTS24
          </h2>
        </div>

        <div className="border-t border-gray-100 px-6 py-5">
          <div className="max-w-[1100px] mx-auto flex flex-col sm:flex-row items-center justify-between gap-3">
            <div className="flex items-center gap-2.5">
              <Image src="/kesher.png" alt="AGENTS24" width={20} height={20} className="h-5 w-5 rounded" />
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
