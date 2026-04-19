"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { AnimatePresence, motion, useMotionTemplate, useMotionValueEvent, useReducedMotion, useScroll, useTransform, animate } from "motion/react";
import { type Repulsor } from "./v9/ParticleField";
import { DOMAIN_SCREENSHOTS, PLATFORM_DOMAINS, PLATFORM_DOMAIN_SCROLL_MODEL, getPlatformDomainsSceneHeight } from "./v9/platformDomains";
import { LandingFooter } from "@/components/marketing/landing-footer";
import { authService } from "@/services";
import { useIsMobile } from "@/hooks/use-mobile";
import { useHeaderStore } from "@/lib/store/useHeaderStore";

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
  logoStartTop: 650,
  logoStartSize: 228,
  topArcHeight: 140,
  seamY: 590,
  apexYOpen: 190,
  sceneHeight: "205vh",
  logoFinalTop: 92,
  logoFinalRight: 20,
  logoFinalSize: 78,
};

const DESKTOP_METRICS: HeroMetrics = {
  logoStartTop: 647,
  logoStartSize: 560,
  topArcHeight: 108,
  seamY: 560,
  apexYOpen: 260,
  sceneHeight: "220vh",
  logoFinalTop: 96,
  logoFinalRight: 28,
  logoFinalSize: 88,
};

/* ═══════════════════════════════════════════════════════════
   DOMAIN TEXT CONTENT — Floating Minimalist Layout
   ═══════════════════════════════════════════════════════════ */
function DomainTextContent({
  domain,
}: {
  domain: (typeof PLATFORM_DOMAINS)[number];
}) {
  return (
    <motion.div
      initial={{ opacity: 0, x: 20, y: 30 }}
      animate={{ opacity: 1, x: 0, y: 0 }}
      exit={{ opacity: 0, x: -10, y: -20 }}
      transition={{ duration: 0.25, ease: [0.19, 1, 0.22, 1] }}
      className="relative w-full h-full"
    >
      {/* Screenshot hero (only top-left needs radius) */}
      <div className="relative w-full h-full rounded-tl-[16px] md:rounded-tl-[22px] overflow-hidden border-l border-t border-black/[0.04] bg-[#fdfdfd]">
        <Image
          src={DOMAIN_SCREENSHOTS[domain.title]}
          alt={domain.title}
          fill
          priority
          placeholder="blur"
          quality={95}
          sizes="(max-width: 768px) 100vw, (max-width: 1200px) 70vw, 1400px"
          className="object-cover object-left-top"
        />
      </div>
    </motion.div>
  );
}

export function LandingV9() {
  const signupUrl = authService.getSignupUrl("/admin/agents/playground");
  const [hasMounted, setHasMounted] = useState(false);
  const [viewportWidth, setViewportWidth] = useState(1440);
  const [vhInstance, setVhInstance] = useState(800);
  const [activeDomainIndex, setActiveDomainIndex] = useState(0);
  const [domainsScenePhase, setDomainsScenePhase] = useState<"before" | "active" | "after">("before");
  const heroSceneRef = useRef<HTMLElement | null>(null);
  const domainsSceneRef = useRef<HTMLElement | null>(null);
  const closingSceneRef = useRef<HTMLElement | null>(null);
  const footerRef = useRef<HTMLElement | null>(null);
  const domainsContainerRef = useRef<HTMLDivElement | null>(null);
  const prefersReducedMotion = useReducedMotion();
  const isMobile = useIsMobile();

  // Particle data — mutable refs, never trigger re-renders
  const particleRepulsorsRef = useRef<Repulsor[]>([]);

  const setHeaderScrolled = useHeaderStore((state) => state.setScrolled);
  const setOnSelectDomain = useHeaderStore((state) => state.setOnSelectDomain);

  useEffect(() => {
    const onScroll = () => {
      const isScrolled = window.scrollY > 40;
      setHeaderScrolled(isScrolled);
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [setHeaderScrolled]);

  // Sync onSelectDomain with the layout once on mount
  useEffect(() => {
    setOnSelectDomain(handleDomainClick);
    return () => setOnSelectDomain(null);
  }, [setOnSelectDomain]);

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
    setHasMounted(true);
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
  const shouldBindSceneScroll = hasMounted && !isMobile;

  const { scrollYProgress } = useScroll({
    target: shouldBindSceneScroll ? heroSceneRef : undefined,
    offset: ["start start", "end end"],
  });
  const { scrollYProgress: domainsScrollProgress } = useScroll({
    target: shouldBindSceneScroll ? domainsSceneRef : undefined,
    offset: ["start start", "end end"],
  });
  const { scrollYProgress: closingScrollProgress } = useScroll({
    target: shouldBindSceneScroll ? closingSceneRef : undefined,
    offset: ["start end", "end start"], // distance = 200vh total for a 100vh section
  });

  const rawProgress = useTransform(scrollYProgress, (value) => {
    if (prefersReducedMotion) return 0;
    if (value <= 0.42) return 0;
    if (value >= 0.76) return 1;
    return (value - 0.42) / 0.34;
  });

  const logoTravelProgress = useTransform(scrollYProgress, (value) => {
    if (prefersReducedMotion) return 0;
    if (value <= 0.42) return 0;
    if (value >= 1) return 1;
    return (value - 0.42) / 0.58;
  });

  const notchApexY = useTransform(rawProgress, [0, 1], [metrics.apexYOpen, metrics.seamY]);
  const leftInnerX = useTransform(rawProgress, [0, 1], [isMobile ? 475 : 475, 600]);
  const rightInnerX = useTransform(rawProgress, [0, 1], [isMobile ? 965 : 965, 840]);
  
  const maxScrollY = isMobile ? (1.05 * vhInstance) : (1.2 * vhInstance);
  const logoRestTop = useTransform(scrollYProgress, (progress) => {
    const p = Math.min(progress, 0.42); 
    return metrics.logoStartTop - (p * maxScrollY);
  });
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
  const logoRotate = useTransform(logoTravelProgress, [0, 1], [0, 420]);
  const effectiveDomainsProgress = useTransform(
    domainsScrollProgress,
    PLATFORM_DOMAIN_SCROLL_MODEL.inputRange,
    PLATFORM_DOMAIN_SCROLL_MODEL.outputRange,
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

  // --- Exit Transition Logic ---
  // Start the exit only after the last domain has had time to settle.
  const lastDomainHoldPoint =
    PLATFORM_DOMAIN_SCROLL_MODEL.clickTargets[PLATFORM_DOMAIN_SCROLL_MODEL.clickTargets.length - 1] ?? 0.94;
  const exitStart = Math.min(0.975, lastDomainHoldPoint + 0.025);
  const exitProgress = useTransform(domainsScrollProgress, [exitStart, 1], [0, 1]);
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

  const startLogoOpacity = useTransform(
    scrollYProgress,
    (v) => (v as number) < 0.42 ? 1 : 0
  );

  const univLogoOpacity = useTransform(
    [scrollYProgress, closingScrollProgress],
    ([heroP, closingP]) => {
      if ((heroP as number) < 0.42) return 0;
      if ((closingP as number) >= 0.5) return 0;
      return 1;
    }
  );

  const staticLogoOpacity = useTransform(
    closingScrollProgress,
    (v) => (v as number) >= 0.5 ? 1 : 0
  );
  const univLogoTranslateX = useTransform(univLogoSize, (s) => -(s as number) / 2);

  // --- Footer "S24" split animation ---
  const { scrollYProgress: footerScrollProgress } = useScroll({
    target: shouldBindSceneScroll ? footerRef : undefined,
    offset: ["start end", "end end"],
  });
  const s24TranslateX = useTransform(footerScrollProgress, [0.3, 1], [0, 120]);

  useMotionValueEvent(effectiveDomainsProgress, "change", (value) => {
    const nextIndex = Math.min(
      PLATFORM_DOMAINS.length - 1,
      Math.max(0, Math.round(value * (PLATFORM_DOMAINS.length - 1))),
    );
    setActiveDomainIndex(nextIndex);
  });

  const handleDomainClick = (index: number) => {
    if (!domainsSceneRef.current) return;
    const rect = domainsSceneRef.current.getBoundingClientRect();
    const absTop = window.scrollY + rect.top;
    const scrollableDistance = rect.height - window.innerHeight;
    
    const targetProgress = PLATFORM_DOMAIN_SCROLL_MODEL.clickTargets[index] ?? PLATFORM_DOMAIN_SCROLL_MODEL.clickTargets[0];
    const targetY = absTop + (scrollableDistance * targetProgress);
    
    // Disable native CSS smooth scroll temporarily so our JS animation can run without fighting it
    const htmlEl = document.documentElement;
    const bodyEl = document.body;
    const htmlOriginal = htmlEl.style.scrollBehavior;
    const bodyOriginal = bodyEl.style.scrollBehavior;
    htmlEl.style.scrollBehavior = 'auto';
    bodyEl.style.scrollBehavior = 'auto';

    // Use JS-driven scroll animation to prevent browser scroll abortion during layout shifts
    animate(window.scrollY, targetY, {
      duration: 0.7,
      ease: [0.16, 1, 0.3, 1], // Custom snappy but smooth easing
      onUpdate: (latest) => window.scrollTo(0, latest),
      onComplete: () => {
        htmlEl.style.scrollBehavior = htmlOriginal;
        bodyEl.style.scrollBehavior = bodyOriginal;
      }
    });
  };

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
  }, [univLogoTop, univLogoLeft, univLogoSize]);

  useMotionValueEvent(univLogoTop, "change", updateRepulsors);

  const bottomNotchPath = useMotionTemplate`M0 ${metrics.seamY}
                   C 70 ${metrics.seamY}, 140 ${metrics.seamY}, 210 ${metrics.seamY}
                   C 370 ${metrics.seamY}, ${leftInnerX} ${notchApexY}, 720 ${notchApexY}
                   C ${rightInnerX} ${notchApexY}, 1070 ${metrics.seamY}, 1230 ${metrics.seamY}
                   C 1300 ${metrics.seamY}, 1370 ${metrics.seamY}, 1440 ${metrics.seamY}
                   L1440 560
                   L0 560
                   Z`;

  if (!hasMounted) {
    return null;
  }

  if (isMobile) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-[#0a0a0a] px-6 text-white">
        <div className="max-w-sm text-center">
          <p className="text-[11px] font-semibold uppercase tracking-[0.28em] text-white/45">
            Temporary Access
          </p>
          <h1 className="mt-4 text-3xl font-semibold tracking-[-0.04em]">
            Available only on PC
          </h1>
          <p className="mt-3 text-sm leading-6 text-white/65">
            Please open this page from a desktop or laptop for now.
          </p>
        </div>
      </main>
    );
  }

  return (
    <div className="min-h-screen bg-white font-sans overflow-x-hidden selection:bg-black/10">
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Archivo+Black&family=Playfair+Display:wght@400;700;900&family=JetBrains+Mono:wght@300;400;500&family=Sora:wght@300;400;600;700&family=DM+Serif+Display&display=swap');
        
        html, body {
          background-color: #0a0a0a;
          scroll-behavior: smooth;
        }
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
        @keyframes blink { 0%,100%{opacity:1} 50%{opacity:0} }
        .cursor-blink { animation: blink 1.1s step-end infinite; }
        @keyframes typewriter { from{width:0} to{width:100%} }
        @keyframes orbitSlow { from{transform:rotate(0deg)} to{transform:rotate(360deg)} }
      `}</style>

      {/* LandingHeader removed here; now managed by the layout using useHeaderStore */}

      {/* UNIVERSAL LOGO — One element, entire journey */}
      <motion.div
        className="fixed z-30 pointer-events-none"
        style={{
          top: univLogoTop,
          left: univLogoLeft,
          width: univLogoSize,
          height: univLogoSize,
          x: univLogoTranslateX,
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
        {/* Native Start Logo - identically natively scrolls with the page, resolving 100% of compositor jitter before handing off to the fixed logo */}
        <motion.div
           className="absolute pointer-events-none"
           style={{
             top: metrics.logoStartTop,
             left: viewportWidth / 2,
             width: metrics.logoStartSize,
             height: metrics.logoStartSize,
             x: -(metrics.logoStartSize / 2),
             opacity: startLogoOpacity,
             zIndex: 30,
           }}
        >
            <Image src="/kesher.png" alt="AGENTS24" width={560} height={560} className="h-full w-full object-contain" priority />
        </motion.div>

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
            
            <div className="hero-2 mt-8 mb-8 flex flex-col items-center">
              <span className="text-[72px] sm:text-[96px] md:text-[130px] font-black leading-[0.85] tracking-tighter text-white/[0.04] select-none" style={{ fontFamily: "'Archivo Black', sans-serif" }}>CONTROL</span>
              <h1 className="-mt-6 md:-mt-10 text-[44px] sm:text-[52px] md:text-[72px] font-medium leading-[1.08] tracking-tight text-white">
                Every agent. Every token.
                <br />
                <span className="inline-flex items-center">
                  <Image src="/kesher.png" alt="O" width={64} height={64} className="w-[32px] h-[32px] sm:w-[38px] sm:h-[38px] md:w-[54px] md:h-[54px] object-contain mr-[1.5px] md:mr-[3px] translate-y-[2px] md:translate-y-[4px] brightness-0 invert" />
                  <span>ne</span>
                </span> single surface.
              </h1>
            </div>
            
            <p className="hero-3 mb-10 max-w-lg text-[16px] leading-relaxed text-[#a1a1aa] md:text-[17px]">
              Build agents, manage knowledge, govern tokens.
              <br className="hidden md:block" />
              One platform. Zero fragmentation.
            </p>

            <div className="hero-4 mb-32" />
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
          style={{ height: getPlatformDomainsSceneHeight(isMobile) }}
        >
          <div
            ref={domainsContainerRef}
            className={`h-screen overflow-visible bg-white ${domainsScenePhase === "active"
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
                      className="relative left-[130px] w-[240px] text-left cursor-pointer group"
                      onClick={() => handleDomainClick(index)}
                    >
                      <motion.p
                        layout="position"
                        className={`text-[19px] font-medium tracking-tight transition-colors duration-300 ${index === activeDomainIndex ? "text-[#0a0a0a]" : "text-[#0a0a0a]/28 group-hover:text-[#0a0a0a]/50"
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
                              transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
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
                    <div className="absolute inset-0 -left-6 -top-6 md:-left-12 md:-top-12 bg-[#f4f4f5] rounded-tl-[24px] md:rounded-tl-[32px]" />

                    {/* Animate individual screenshots over the persistent bg */}
                    <AnimatePresence mode="wait">
                      <DomainTextContent
                        key={activeDomainIndex}
                        domain={PLATFORM_DOMAINS[activeDomainIndex]}
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
          className="relative bg-white z-10 pt-px w-full"
          style={{ height: vhInstance }}
        >
          {/* Static Landed Logo - seamlessly replaces the fixed logo to eliminate bounding jitter natively */}
          <motion.div
            className="absolute pointer-events-none"
            style={{
              top: verticalMiddle,
              left: viewportWidth / 2,
              width: metrics.logoStartSize,
              height: metrics.logoStartSize,
              x: -(metrics.logoStartSize / 2),
              opacity: staticLogoOpacity,
              zIndex: 30,
            }}
          >
            <Image 
              src="/kesher.png" 
              alt="AGENTS24" 
              width={560} 
              height={560} 
              className="h-full w-full object-contain" 
              priority
            />
          </motion.div>

          {/* The Black Section Base */}
          <div
            className="absolute inset-x-0 bottom-0 bg-[#0a0a0a] z-10 pointer-events-auto"
            style={{ top: verticalMiddle + metrics.logoStartSize * 0.52 + svgH - 1 }}
          >
            {/* SVG Hexagonal Dent - sits exactly on top of the black base */}
            <div className="absolute z-0 bottom-[calc(100%-1px)] left-0 right-0 overflow-hidden flex justify-center pointer-events-none" style={{ height: svgH }}>
              <svg width={svgW} height={svgH} viewBox={`0 0 ${svgW} ${svgH}`} className="shrink-0">
                <path d={dentPath} fill="#0a0a0a" />
              </svg>
              {/* Invisible side extensions for ultra-widescreen */}
              <div className="absolute right-1/2 mr-[600px] w-[50vw] h-full bg-[#0a0a0a]" />
              <div className="absolute left-1/2 ml-[600px] w-[50vw] h-full bg-[#0a0a0a]" />
            </div>
          </div>

          {/* Split Content (Left: Liftoff, Right: CTA) — Sibling for clean layering */}
          <div
            className="absolute inset-x-0 z-20 w-full max-w-[1240px] mx-auto px-8 flex flex-col md:flex-row items-center md:items-start justify-between pointer-events-auto"
            style={{ top: verticalMiddle + metrics.logoStartSize * 0.52 + 60 }}
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
              <a href={signupUrl} className="px-8 py-3.5 bg-white text-black text-[15px] font-semibold rounded-full hover:bg-gray-100 transition-colors shadow-lg hover:shadow-xl hover:-translate-y-1 transform duration-300">
                Build your first agent
              </a>
            </div>
          </div>
        </section>
      </main>

      <footer ref={footerRef} className="bg-[#0a0a0a] relative z-50">
        <LandingFooter onSelectDomain={handleDomainClick} />

        <div className="px-6 pb-6 relative overflow-hidden">
          <h2
            className="text-[20vw] md:text-[14vw] font-black tracking-tighter text-white leading-[0.85] select-none whitespace-nowrap"
            style={{ 
              fontFamily: "'Archivo Black', sans-serif",
              maskImage: 'linear-gradient(to right, black 70%, transparent 100%)',
              WebkitMaskImage: 'linear-gradient(to right, black 70%, transparent 100%)'
            }}
          >
            <span>AGENT</span>
            <motion.span
              style={{ x: s24TranslateX, display: 'inline-block' }}
            >
              S24
            </motion.span>
          </h2>
        </div>

        <div className=" px-6 py-5">
          <div className="max-w-[1100px] mx-auto flex flex-col sm:flex-row items-center justify-between gap-3">
          </div>
        </div>

      </footer>

    </div>
  );
}
