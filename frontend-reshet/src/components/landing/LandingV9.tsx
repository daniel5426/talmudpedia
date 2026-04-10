"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { AnimatePresence, motion, useMotionTemplate, useMotionValueEvent, useReducedMotion, useScroll, useTransform } from "motion/react";
import { ArrowRight, ChevronDown } from "lucide-react";
import { ParticleField, type Repulsor, type ClearZone } from "./v9/ParticleField";

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
    statLabel: "Active graphs",
    statValue: "124",
  },
  {
    title: "Knowledge",
    eyebrow: "Retrieval",
    heading: "Attach structured knowledge pipelines directly to the platform that serves production agents.",
    body: "Keep ingestion, retrieval, source management, and operator-level control in the same operating layer as your deployed agents.",
    points: ["Source pipelines", "Operator tuning", "Index governance", "Answer grounding"],
    statLabel: "Indexed sources",
    statValue: "18.4K",
  },
  {
    title: "Governance",
    eyebrow: "Control",
    heading: "Track cost, permissions, and model behavior with explicit platform rules instead of ad-hoc conventions.",
    body: "Make runtime budgets, model policy, resource controls, and operator boundaries first-class platform primitives.",
    points: ["Quota policy", "Scope control", "Model routing", "Usage accounting"],
    statLabel: "Guardrails enforced",
    statValue: "31",
  },
  {
    title: "Deployments",
    eyebrow: "Runtime",
    heading: "Move from local iteration to deployed runtime surfaces without losing visibility or control.",
    body: "Ship hosted experiences, embedded runtimes, and managed app surfaces from the same platform backbone.",
    points: ["Hosted apps", "Embedded runtime", "Preview flow", "Release controls"],
    statLabel: "Live environments",
    statValue: "52",
  },
] as const;

const DOMAIN_SCREENSHOTS = [
  "/platform_screenshot/Screenshot 2026-03-23 at 22.50.52.png",
  "/platform_screenshot/Screenshot 2026-03-23 at 22.49.30.png",
  "/platform_screenshot/Screenshot 2026-03-23 at 22.58.34.png",
  "/platform_screenshot/Screenshot 2026-03-23 at 22.59.00.png",
] as const;


/* ═══════════════════════════════════════════════════════════
   DOMAIN TEXT CONTENT — Floating Minimalist Layout
   ═══════════════════════════════════════════════════════════ */
function DomainTextContent({
  domain,
  index,
}: {
  domain: (typeof PLATFORM_DOMAINS)[number];
  index: number;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, x: 20, y: 30 }}
      animate={{ opacity: 1, x: 0, y: 0 }}
      exit={{ opacity: 0, x: -10, y: -20 }}
      transition={{ duration: 0.4, ease: [0.19, 1, 0.22, 1] }}
      className="relative w-full h-full"
    >
      {/* Screenshot hero (only top-left needs radius) */}
      <div className="relative w-full h-full rounded-tl-[24px] md:rounded-tl-[32px] overflow-hidden border-l border-t border-black/[0.04] bg-[#fdfdfd]">
        <Image
          src={DOMAIN_SCREENSHOTS[index]}
          alt={domain.title}
          fill
          className="object-cover object-left-top"
        />
      </div>
    </motion.div>
  );
}

export function LandingV9() {
  const [scrolled, setScrolled] = useState(false);
  const [isMobile, setIsMobile] = useState(false);
  const [viewportWidth, setViewportWidth] = useState(1440);
  const [vhInstance, setVhInstance] = useState(800);
  const [activeDomainIndex, setActiveDomainIndex] = useState(0);
  const [domainsScenePhase, setDomainsScenePhase] = useState<"before" | "active" | "after">("before");
  const heroSceneRef = useRef<HTMLElement | null>(null);
  const domainsSceneRef = useRef<HTMLElement | null>(null);
  const closingSceneRef = useRef<HTMLElement | null>(null);
  const domainsContainerRef = useRef<HTMLDivElement | null>(null);
  const prefersReducedMotion = useReducedMotion();

  // Particle data — mutable refs, never trigger re-renders
  const particleRepulsorsRef = useRef<Repulsor[]>([]);

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
    const update = () => {
      setViewportWidth(window.innerWidth);
      setVhInstance(window.innerHeight);
    };
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
  const { scrollYProgress: closingScrollProgress } = useScroll({
    target: closingSceneRef,
    offset: ["start end", "end start"], // distance = 200vh total for a 100vh section
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
  
  // Calculate left side anchor for the logo (closer to the left edge of the page)
  const finalLeftAnchor = Math.max(24, (viewportWidth - 1580) / 2 + 24) + 60;
  
  const logoLeft = useTransform(
    logoTravelProgress,
    [0, 1],
    [viewportWidth / 2, finalLeftAnchor],
  );
  const logoX = useTransform(logoSize, (value) => -value / 2);
  const logoRotate = useTransform(logoTravelProgress, [0, 1], [0, 420]);
  const logoOpacity = useTransform(rawProgress, [0, 0.12, 1], [1, 1, 1]);
  const domainStops = PLATFORM_DOMAINS.map((_, index) => index / (PLATFORM_DOMAINS.length - 1));
  // Staircase transform: Creates 4 distinct 'stops' where the UI lingers on a domain.
  // Each domain gets a stay period, then a transition to the next.
  const effectiveDomainsProgress = useTransform(
    domainsScrollProgress,
    [0, 0.15, 0.25, 0.40, 0.50, 0.65, 0.75, 1.0], // Input scroll segments
    [0, 0,    0.333, 0.333, 0.666, 0.666, 1,    1]    // Output to domain indices
  );

  // Layout Constants for dynamic tracking
  const TITLE_H = 28; // Matches actual line-height of text-[19px]
  const GAP_H = 32; // Matches gap-8
  const SUBTEXT_H = 58; // 2 lines at 20px + 12px mt + buffer

  // Dynamic Center Calculation:
  // We want the logo's TOP EDGE to follow the trajectory needed to keep its center on the title.
  const getLogoYForIndex = (index: number, activeIdx: number) => {
    // baseTop is the exact Top Edge where the hero lands.
    const baseTop = metrics.logoFinalTop;
    const expansionOffset = index > activeIdx ? SUBTEXT_H : 0;
    
    // We simply calculate the TOP of the logo.
    // At index 0, it returns exactly baseTop (matching hero landing).
    return baseTop + index * (TITLE_H + GAP_H) + expansionOffset;
  };

  const domainLogoTop = useTransform(effectiveDomainsProgress, (value) => {
    const activeIdx = value * (PLATFORM_DOMAINS.length - 1);
    const i1 = Math.floor(activeIdx);
    const i2 = Math.ceil(activeIdx);
    const f = activeIdx - i1;

    // Interpolate logo between "Logo centered on title i1 (with i1 expanded)"
    // and "Logo centered on title i2 (with i2 expanded)".
    const y1 = getLogoYForIndex(i1, i1);
    const y2 = getLogoYForIndex(i2, i2);

    return y1 + (y2 - y1) * f;
  });

  const domainLogoRotate = useTransform(domainsScrollProgress, [0, 0.12, 1], [420, 420 + 60, 420 + 480]);
  const domainLogoOpacity = useTransform(domainsScrollProgress, [0, 0.08, 1], [0, 1, 1]);

  // --- Exit Transition Logic ---
  // As we reach the end of the section (0.9 to 1.0), the big elements shrink/fade
  const exitProgress = useTransform(domainsScrollProgress, [0.88, 1], [0, 1]);
  const exitScale = useTransform(exitProgress, [0, 1], [1, 0.82]);
  const exitX = useTransform(exitProgress, [0, 1], [0, -40]);
  const exitOpacity = useTransform(exitProgress, [0, 0.6, 1], [1, 1, 0]);

  // --- Universal Logo Integration (Zero-Fade Journey) ---
  const finalDomainTop = getLogoYForIndex(PLATFORM_DOMAINS.length - 1, PLATFORM_DOMAINS.length - 1);
  const verticalMiddle = vhInstance / 2 - metrics.logoStartSize / 2;

  // --- Dent Math (Hexagonal Fit) ---
  const topW = metrics.logoStartSize * 0.95;
  const dentD = metrics.logoStartSize * 0.45;
  const botW = metrics.logoStartSize * 0.63; // Widened flat bottom upon request
  const svgW = 1200;
  const svgH = dentD + 30; 
  const cX = svgW / 2;
  const tL = cX - topW / 2;
  const tR = cX + topW / 2;
  const bL = cX - botW / 2;
  const bR = cX + botW / 2;

  const dentPath = `
    M 0 ${svgH}
    L 0 0
    L ${tL - 40} 0
    C ${tL - 15} 0, ${tL} 10, ${tL + 10} 30
    L ${bL - 10} ${dentD - 20}
    C ${bL} ${dentD}, ${bL + 15} ${dentD}, ${bL + 40} ${dentD}
    L ${bR - 40} ${dentD}
    C ${bR - 15} ${dentD}, ${bR} ${dentD}, ${bR + 10} ${dentD - 20}
    L ${tR - 10} 30
    C ${tR} 10, ${tR + 15} 0, ${tR + 40} 0
    L ${svgW} 0
    L ${svgW} ${svgH}
    Z
  `;

  const closingLogoTop = useTransform(
    closingScrollProgress,
    [0, 0.5, 1], // 0.5 is when the 100vh section fully fills the viewport
    [
      finalDomainTop,
      verticalMiddle,
      verticalMiddle - vhInstance
    ]
  );
  const closingLogoLeft = useTransform(closingScrollProgress, [0, 0.5, 1], [finalLeftAnchor, viewportWidth / 2, viewportWidth / 2]);
  const closingLogoSize = useTransform(closingScrollProgress, [0, 0.5, 1], [metrics.logoFinalSize, metrics.logoStartSize, metrics.logoStartSize]);
  const closingLogoRotate = useTransform(closingScrollProgress, [0, 0.5, 1], [900, 1440, 1440]);

  const univLogoTop = useTransform(
    [logoTop, domainLogoTop, closingLogoTop, domainsScrollProgress, closingScrollProgress],
    ([hT, dT, cT, dP, cP]) => {
      if ((cP as number) > 0) return cT as number;
      if ((dP as number) > 0) return dT as number;
      return hT as number;
    }
  );
  
  const univLogoLeft = useTransform(
    [logoLeft, closingLogoLeft, domainsScrollProgress, closingScrollProgress],
    ([hL, cL, dP, cP]) => {
      if ((cP as number) > 0) return cL as number;
      if ((dP as number) > 0) return finalLeftAnchor;
      return hL as number;
    }
  );

  const univLogoSize = useTransform(
    [logoSize, closingLogoSize, domainsScrollProgress, closingScrollProgress],
    ([hS, cS, dP, cP]) => {
      if ((cP as number) > 0) return cS as number;
      if ((dP as number) > 0) return metrics.logoFinalSize;
      return hS as number;
    }
  );

  const univLogoRotate = useTransform(
    [logoRotate, domainLogoRotate, closingLogoRotate, domainsScrollProgress, closingScrollProgress],
    ([hR, dR, cR, dP, cP]) => {
      if ((cP as number) > 0) return cR as number;
      if ((dP as number) > 0) return dR as number;
      return hR as number;
    }
  );
  
  const univLogoOpacity = useTransform(rawProgress, [0, 0.12, 1], [1, 1, 1]); // Stays at 1 throughout

  useMotionValueEvent(effectiveDomainsProgress, "change", (value) => {
    const nextIndex = Math.min(
      PLATFORM_DOMAINS.length - 1,
      Math.max(0, Math.round(value * (PLATFORM_DOMAINS.length - 1))),
    );
    setActiveDomainIndex(nextIndex);
  });

  // ── Logo repulsor for particles ──
  // Writes directly to ref — zero re-renders. Tracks both the main logo and domain logo.
  const updateRepulsors = useCallback(() => {
    const container = domainsContainerRef.current;
    if (!container) return;
    const containerRect = container.getBoundingClientRect();
    const reps: Repulsor[] = [];

    // Universal Logo Repulsor
    const currentTop = univLogoTop.get();
    const currentLeft = univLogoLeft.get();
    const currentSize = univLogoSize.get();
    const relY = currentTop - containerRect.top + currentSize / 2;
    if (relY > -currentSize && relY < containerRect.height + currentSize) {
      reps.push({ x: currentLeft - containerRect.left, y: relY, radius: currentSize * 1.8, strength: 1.2 });
    }

    particleRepulsorsRef.current = reps;
  }, [univLogoTop, univLogoLeft, univLogoSize, metrics.logoFinalSize]);

  useMotionValueEvent(univLogoTop, "change", updateRepulsors);

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
              ? "max-w-4xl bg-white/90 backdrop-blur-xl rounded-full border border-gray-200/60 px-5"
              : "max-w-[1200px] bg-transparent px-6"
          }`}
        >
          <Link href="/" className="flex items-center gap-2.5">
            <Image src="/kesher.png" alt="AGENTS24" width={28} height={28} className="h-7 w-7 rounded-lg" />
            <span className="text-lg font-bold tracking-tight text-white mix-blend-difference">AGENTS24</span>
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

      {/* UNIVERSAL LOGO — One element, entire journey */}
      <motion.div
        className="fixed z-40 pointer-events-none"
        style={{
          top: univLogoTop,
          left: univLogoLeft,
          width: univLogoSize,
          height: univLogoSize,
          x: useTransform(univLogoSize, (s) => -(s as number) / 2),
          rotate: univLogoRotate,
          opacity: univLogoOpacity,
        }}
      >
        <Image src="/kesher.png" alt="AGENTS24" width={560} height={560} className="h-full w-full object-contain" priority />
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

      <main className="relative -mt-[62vh] bg-white md:-mt-[68vh]">
        <section
          ref={domainsSceneRef}
          id="platform"
          className="relative"
          style={{ height: isMobile ? "400vh" : "700vh" }}
        >
          <div
            ref={domainsContainerRef}
            className={`h-screen overflow-visible bg-white ${
              domainsScenePhase === "active"
                ? "fixed inset-x-0 top-0 z-20"
                : "absolute inset-x-0 z-20"
            } ${domainsScenePhase === "before" ? "top-0" : ""} ${domainsScenePhase === "after" ? "bottom-0" : ""}`}
          >
            <div className="relative z-10 mx-auto grid h-full max-w-[1580px] gap-10 px-6 md:grid-cols-[340px_minmax(0,1fr)] md:gap-16">
              
              {/* Left Column: Flowing Logo & Domain Labels (Dynamic Accordion) */}
              <div className="relative hidden self-start md:block">
                <div 
                  className="flex flex-col gap-8"
                  style={{ 
                    paddingTop: (metrics.logoFinalTop + metrics.logoFinalSize / 2) - (TITLE_H / 2) - 1
                  }}
                >
                  {PLATFORM_DOMAINS.map((domain, index) => (
                    <motion.div
                      layout
                      key={domain.title}
                      className="relative left-[130px] w-[240px] text-left"
                    >
                      <motion.p 
                        layout="position"
                        className={`text-[19px] font-medium tracking-tight transition-colors duration-300 ${
                          index === activeDomainIndex ? "text-[#0a0a0a]" : "text-[#0a0a0a]/28"
                        }`}
                      >
                        {domain.title}
                      </motion.p>
                      
                      {/* Expanding subtext section */}
                      <div className="overflow-hidden">
                        <AnimatePresence>
                          {index === activeDomainIndex && (
                            <motion.p 
                              layout
                              initial={{ height: 0, opacity: 0, marginTop: 0 }}
                              animate={{ height: "auto", opacity: 1, marginTop: 12 }}
                              exit={{ height: 0, opacity: 0, marginTop: 0 }}
                              transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
                              className="text-[14px] leading-relaxed text-[#0a0a0a]/40 pr-8"
                            >
                              {domain.body}
                            </motion.p>
                          )}
                        </AnimatePresence>
                      </div>
                    </motion.div>
                  ))}
                </div>
              </div>

              {/* Right Column: Active Domain Content */}
              <div className="relative flex min-h-0 items-center justify-center py-20 md:py-28">
                {/* Persistent Layout Wrapper */}
                <motion.div 
                  style={{ scale: exitScale, x: exitX, opacity: exitOpacity }}
                  className="absolute top-[20vh] lg:top-[16vh] left-[60px] md:left-[60px] w-[120vw] md:w-[90vw] lg:w-[1400px] h-[80vh] md:h-[90vh] lg:h-[1000px]"
                >
                  <div className="relative w-full h-full">
                    {/* Soft background padding (STATIONARY — shared across all domains) */}
                    <div className="absolute inset-0 -left-6 -top-6 md:-left-12 md:-top-12 bg-[#f4f4f5] rounded-tl-[40px] md:rounded-tl-[56px]" />
                    
                    {/* Animate individual screenshots over the persistent bg */}
                    <AnimatePresence mode="wait">
                      <DomainTextContent
                        key={activeDomainIndex}
                        domain={PLATFORM_DOMAINS[activeDomainIndex]}
                        index={activeDomainIndex}
                      />
                    </AnimatePresence>
                  </div>
                </motion.div>
              </div>
            </div>
          </div>
        </section>

        {/* --- Post-Domains Transition: Closing Sequence --- */}
        <section 
          ref={closingSceneRef} 
          className="relative bg-white pt-px w-full" 
          style={{ height: "100vh" }}
        >
           {/* The Black Section Base */}
           <div 
             className="absolute inset-x-0 bottom-0 bg-[#0a0a0a] pointer-events-auto" 
             style={{ top: verticalMiddle + metrics.logoStartSize * 0.52 + svgH - 1 }}
           >
              {/* SVG Hexagonal Dent - sits exactly on top of the black base */}
              <div className="absolute bottom-[calc(100%-1px)] left-0 right-0 overflow-hidden flex justify-center pointer-events-none" style={{ height: svgH }}>
                <svg width={svgW} height={svgH} viewBox={`0 0 ${svgW} ${svgH}`} className="shrink-0">
                  <path d={dentPath} fill="#0a0a0a" />
                </svg>
                {/* Invisible side extensions for ultra-widescreen */}
                <div className="absolute right-1/2 mr-[600px] w-[50vw] h-full bg-[#0a0a0a]" />
                <div className="absolute left-1/2 ml-[600px] w-[50vw] h-full bg-[#0a0a0a]" />
              </div>

              {/* Split Content (Left: Liftoff, Right: CTA) */}
              <div 
                className="absolute inset-x-0 z-20 w-full max-w-[1240px] mx-auto px-8 flex flex-col md:flex-row items-center md:items-start justify-between pointer-events-auto"
                style={{ top: -svgH + 60 }}
              >
                 {/* Left Side */}
                 <div className="text-center md:text-left mt-2">
                   <p className="text-3xl md:text-[40px] font-medium tracking-tight text-white leading-tight">
                     Experience
                     <br />
                     liftoff.
                   </p>
                 </div>
                 
                 {/* Right Side */}
                 <div className="flex flex-col items-center md:items-end text-center md:text-right mt-1">
                   <h2 className="text-[20px] md:text-2xl font-medium tracking-tight text-white mb-5">
                     Ready to deploy?
                   </h2>
                   <Link href="/auth/signup" className="px-8 py-3.5 bg-white text-black text-[15px] font-semibold rounded-full hover:bg-gray-100 transition-colors shadow-lg hover:shadow-xl hover:-translate-y-1 transform duration-300">
                     Build your first agent 
                   </Link>
                 </div>
              </div>
           </div>
        </section>
      </main>

      <footer className="bg-[#0a0a0a]">
        <div className="max-w-[1100px] mx-auto px-6 py-14">
          <div className="grid grid-cols-2 md:grid-cols-5 gap-10">
            <div className="col-span-2 md:col-span-1">
              {/* Empty column to preserve 5-col grid structure (Liftoff text moved up) */}
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
                      <Link href={link.href} className="text-sm text-gray-400 hover:text-white transition-colors">
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
            className="text-[18vw] md:text-[14vw] font-black tracking-tighter text-white leading-[0.85] select-none"
            style={{ fontFamily: "system-ui, -apple-system, sans-serif" }}
          >
            AGENTS24
          </h2>
        </div>

        <div className="border-t border-white/10 px-6 py-5">
          <div className="max-w-[1100px] mx-auto flex flex-col sm:flex-row items-center justify-between gap-3">
            <div className="flex items-center gap-2.5">
              <Image src="/kesher.png" alt="AGENTS24" width={20} height={20} className="h-5 w-5 rounded" />
              <span className="text-xs text-gray-500">AGENTS24</span>
            </div>
            <div className="flex items-center gap-6">
              {["About", "Privacy", "Terms"].map((link) => (
                <Link key={link} href="#" className="text-xs text-gray-500 hover:text-white transition-colors">
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
