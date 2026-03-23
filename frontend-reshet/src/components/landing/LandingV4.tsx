"use client";

import Link from "next/link";
import {
  ArrowRight,
  ChartColumnIncreasing,
  GitBranch,
  Layers3,
  MoveRight,
  Radar,
} from "lucide-react";

const workflowSteps = [
  {
    title: "Author the graph",
    copy: "Map agent logic, tools, and branching paths in one builder instead of scattered prompts.",
  },
  {
    title: "Ground with knowledge",
    copy: "Feed the run with ingestion pipelines, stores, and retrieval contracts you can audit later.",
  },
  {
    title: "Ship the product",
    copy: "Publish apps, track revisions, and trace exactly which runtime decisions led to outcomes.",
  },
] as const;

const proofStats = [
  ["18.4K", "monthly runs"],
  ["4.7K", "knowledge hits"],
  ["92%", "tool success rate"],
  ["214", "published revisions"],
] as const;

export function LandingV4() {
  return (
    <div className="relative min-h-screen overflow-hidden bg-[#f3f1eb] text-[#171717] selection:bg-[#111827] selection:text-white">
      <style>{`@import url('https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');`}</style>

      <div className="pointer-events-none fixed inset-0">
        <div className="absolute left-[-10%] top-[8%] h-[26rem] w-[26rem] rounded-full bg-[#cfe7db] blur-[120px]" />
        <div className="absolute right-[-8%] top-[24%] h-[30rem] w-[30rem] rounded-full bg-[#d8d3c4] blur-[140px]" />
      </div>

      <nav className="fixed top-0 z-50 w-full">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-5">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-full bg-[#171717] text-[11px] font-bold text-white">
              TP
            </div>
            <span
              className="text-[14px] font-bold tracking-[-0.03em]"
              style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}
            >
              Talmudpedia
            </span>
          </div>

          <div
            className="hidden items-center gap-8 text-[13px] text-[#171717]/60 md:flex"
            style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}
          >
            <span>Platform</span>
            <span>Analytics</span>
            <span>Customers</span>
            <span>Docs</span>
          </div>

          <Link
            href="/auth/login"
            className="rounded-full border border-[#171717]/12 bg-white/70 px-5 py-2.5 text-[13px] font-semibold text-[#171717] shadow-[0_12px_40px_rgba(23,23,23,0.08)] backdrop-blur-xl transition-all duration-300 hover:border-[#171717]/22"
            style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}
          >
            Book a demo
          </Link>
        </div>
      </nav>

      <section className="px-6 pb-16 pt-32 md:pb-24 md:pt-40">
        <div className="mx-auto grid max-w-7xl gap-12 lg:grid-cols-[0.95fr_1.05fr] lg:items-center">
          <div>
            <p
              className="text-[11px] uppercase tracking-[0.28em] text-[#2d6a4f]"
              style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}
            >
              Dub-inspired product storytelling
            </p>

            <h1
              className="mt-4 max-w-[11ch] text-[clamp(3.2rem,7vw,6rem)] leading-[0.96] tracking-[-0.06em]"
              style={{ fontFamily: "'Instrument Serif', serif" }}
            >
              Measure what your AI product actually changes.
            </h1>

            <p
              className="mt-6 max-w-xl text-[16px] leading-8 text-[#171717]/68"
              style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}
            >
              Talmudpedia connects graph execution, retrieval context, tool calls,
              and published app revisions into one clean product signal. No vanity
              metrics. Just the runtime path to customer outcomes.
            </p>

            <div
              className="mt-8 flex flex-col gap-3 sm:flex-row"
              style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}
            >
              <Link
                href="/auth/login"
                className="group inline-flex items-center justify-center gap-2 rounded-full bg-[#171717] px-7 py-4 text-[14px] font-semibold text-white transition-transform duration-300 hover:-translate-y-0.5"
              >
                Start free
                <ArrowRight className="h-4 w-4 transition-transform duration-300 group-hover:translate-x-1" />
              </Link>
              <Link
                href="/admin/apps"
                className="inline-flex items-center justify-center rounded-full border border-[#171717]/12 bg-white/75 px-7 py-4 text-[14px] font-semibold text-[#171717] backdrop-blur-xl transition-all duration-300 hover:border-[#171717]/24"
              >
                Explore demo
              </Link>
            </div>

            <div
              className="mt-10 flex flex-wrap gap-6 text-[12px] text-[#171717]/52"
              style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}
            >
              <span>Graph compiler</span>
              <span>Run events</span>
              <span>App revisions</span>
              <span>Role-based access</span>
            </div>
          </div>

          <div>
            <div className="grid gap-4 md:grid-cols-[1.05fr_0.95fr]">
              <div className="rounded-[2rem] bg-[#171717] p-6 text-white shadow-[0_40px_100px_rgba(23,23,23,0.18)]">
                <div className="flex items-center justify-between">
                  <div>
                    <p
                      className="text-[11px] uppercase tracking-[0.2em] text-white/45"
                      style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}
                    >
                      App outcome funnel
                    </p>
                    <h2
                      className="mt-2 text-[30px] leading-[1] tracking-[-0.05em]"
                      style={{ fontFamily: "'Instrument Serif', serif" }}
                    >
                      12.8% publish-to-paid
                    </h2>
                  </div>
                  <ChartColumnIncreasing className="h-5 w-5 text-[#9fe3c2]" />
                </div>

                <div className="mt-8 space-y-4">
                  {[
                    ["Runs", "18.4K", "bg-white/18"],
                    ["Qualified sessions", "4.1K", "bg-white/26"],
                    ["Revisions shipped", "214", "bg-[#9fe3c2] text-[#171717]"],
                  ].map(([label, value, classes]) => (
                    <div key={label} className="grid grid-cols-[1fr_auto] items-center gap-3">
                      <span
                        className="text-[12px] uppercase tracking-[0.18em] text-white/50"
                        style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}
                      >
                        {label}
                      </span>
                      <span
                        className={`rounded-full px-3 py-1 text-[12px] font-semibold ${classes}`}
                        style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}
                      >
                        {value}
                      </span>
                    </div>
                  ))}
                </div>

                <div className="mt-8 flex items-end gap-2">
                  {[24, 44, 40, 62, 58, 82, 92].map((value, index) => (
                    <div key={value} className="flex-1">
                      <div
                        className={`rounded-t-[999px] ${index === 6 ? "bg-[#9fe3c2]" : "bg-white/20"}`}
                        style={{ height: `${value}px` }}
                      />
                    </div>
                  ))}
                </div>
              </div>

              <div className="space-y-4">
                <div className="rounded-[2rem] border border-[#171717]/10 bg-white/80 p-5 shadow-[0_20px_50px_rgba(23,23,23,0.06)] backdrop-blur-xl">
                  <div className="flex items-center justify-between">
                    <p
                      className="text-[11px] uppercase tracking-[0.18em] text-[#171717]/45"
                      style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}
                    >
                      Runtime path
                    </p>
                    <Radar className="h-4 w-4 text-[#2d6a4f]" />
                  </div>
                  <div className="mt-4 space-y-3">
                    {["Graph compile", "Knowledge retrieve", "Tool resolve", "App publish"].map((item) => (
                      <div
                        key={item}
                        className="flex items-center justify-between rounded-2xl bg-[#f6f3ed] px-4 py-3"
                      >
                        <span
                          className="text-[13px] text-[#171717]/72"
                          style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}
                        >
                          {item}
                        </span>
                        <MoveRight className="h-4 w-4 text-[#171717]/30" />
                      </div>
                    ))}
                  </div>
                </div>

                <div className="rounded-[2rem] border border-[#171717]/10 bg-[#dfece6] p-5">
                  <p
                    className="text-[11px] uppercase tracking-[0.18em] text-[#2d6a4f]"
                    style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}
                  >
                    Customer proof
                  </p>
                  <p
                    className="mt-3 text-[26px] leading-[1.02] tracking-[-0.04em] text-[#171717]"
                    style={{ fontFamily: "'Instrument Serif', serif" }}
                  >
                    “We finally know which agent behavior drives product adoption.”
                  </p>
                  <p
                    className="mt-4 text-[13px] text-[#171717]/62"
                    style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}
                  >
                    Yael Cohen, Growth Engineering at Meridian
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="px-6 py-16 md:py-24">
        <div className="mx-auto max-w-7xl rounded-[2.2rem] border border-[#171717]/8 bg-white/72 px-6 py-8 shadow-[0_24px_80px_rgba(23,23,23,0.06)] backdrop-blur-xl md:px-8">
          <div className="grid gap-8 lg:grid-cols-[0.85fr_1.15fr]">
            <div>
              <p
                className="text-[11px] uppercase tracking-[0.26em] text-[#2d6a4f]"
                style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}
              >
                It starts with one run
              </p>
              <h2
                className="mt-4 text-[clamp(2.2rem,5vw,4rem)] leading-[0.98] tracking-[-0.05em]"
                style={{ fontFamily: "'Instrument Serif', serif" }}
              >
                From reasoning graph to governed release.
              </h2>
            </div>

            <div className="grid gap-4 md:grid-cols-3">
              {workflowSteps.map((step, index) => (
                <div key={step.title} className="rounded-[1.7rem] bg-[#f6f3ed] p-6">
                  <div
                    className="flex h-10 w-10 items-center justify-center rounded-full bg-[#171717] text-[12px] font-semibold text-white"
                    style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}
                  >
                    0{index + 1}
                  </div>
                  <h3
                    className="mt-5 text-[24px] leading-[1.02] tracking-[-0.04em]"
                    style={{ fontFamily: "'Instrument Serif', serif" }}
                  >
                    {step.title}
                  </h3>
                  <p
                    className="mt-3 text-[14px] leading-7 text-[#171717]/65"
                    style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}
                  >
                    {step.copy}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className="px-6 pb-16 md:pb-24">
        <div className="mx-auto max-w-7xl rounded-[2.2rem] bg-[#171717] px-8 py-10 text-white md:px-10">
          <div className="flex flex-wrap items-center justify-between gap-5">
            <div>
              <p
                className="text-[11px] uppercase tracking-[0.22em] text-white/45"
                style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}
              >
                Measure what matters
              </p>
              <h2
                className="mt-3 text-[clamp(2.2rem,5vw,4rem)] leading-[0.98] tracking-[-0.05em]"
                style={{ fontFamily: "'Instrument Serif', serif" }}
              >
                All your product signals, one board.
              </h2>
            </div>

            <div className="flex items-center gap-2 rounded-full border border-white/12 px-4 py-2 text-[12px] text-white/68">
              <GitBranch className="h-4 w-4" />
              Graphs + RAG + Apps + Governance
            </div>
          </div>

          <div className="mt-8 grid gap-4 md:grid-cols-4">
            {proofStats.map(([value, label]) => (
              <div key={label} className="rounded-[1.6rem] bg-white/6 p-5">
                <p
                  className="text-[11px] uppercase tracking-[0.18em] text-white/42"
                  style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}
                >
                  {label}
                </p>
                <p
                  className="mt-3 text-[32px] tracking-[-0.05em]"
                  style={{ fontFamily: "'Instrument Serif', serif" }}
                >
                  {value}
                </p>
              </div>
            ))}
          </div>

          <div className="mt-6 grid gap-4 lg:grid-cols-[1fr_0.8fr]">
            <div className="rounded-[1.8rem] bg-white/6 p-6">
              <div className="flex items-center justify-between">
                <p
                  className="text-[11px] uppercase tracking-[0.18em] text-white/42"
                  style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}
                >
                  Live event stream
                </p>
                <Layers3 className="h-4 w-4 text-[#9fe3c2]" />
              </div>
              <div className="mt-4 space-y-3">
                {[
                  "run.created · acquisition-assistant",
                  "knowledge.query · 8 passages matched",
                  "tool.success · billing.lookup",
                  "revision.published · partner-portal-v12",
                ].map((item) => (
                  <div key={item} className="rounded-2xl bg-black/18 px-4 py-3 text-[13px] text-white/72">
                    {item}
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-[1.8rem] bg-[#9fe3c2] p-6 text-[#171717]">
              <p
                className="text-[11px] uppercase tracking-[0.18em] text-[#171717]/52"
                style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}
              >
                Why this works
              </p>
              <p
                className="mt-4 text-[30px] leading-[1.02] tracking-[-0.05em]"
                style={{ fontFamily: "'Instrument Serif', serif" }}
              >
                Because AI metrics without runtime context are just noise.
              </p>
            </div>
          </div>
        </div>
      </section>

      <section className="px-6 pb-24 md:pb-32">
        <div className="mx-auto flex max-w-7xl flex-col items-start justify-between gap-6 rounded-[2.2rem] border border-[#171717]/10 bg-white/75 px-8 py-10 shadow-[0_22px_70px_rgba(23,23,23,0.06)] backdrop-blur-xl md:flex-row md:items-center">
          <div>
            <p
              className="text-[11px] uppercase tracking-[0.22em] text-[#2d6a4f]"
              style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}
            >
              Ready to ship?
            </p>
            <h2
              className="mt-3 text-[clamp(2.2rem,5vw,3.8rem)] leading-[0.98] tracking-[-0.05em]"
              style={{ fontFamily: "'Instrument Serif', serif" }}
            >
              Build your AI product with signal, not guesswork.
            </h2>
          </div>

          <div className="flex flex-col gap-3 sm:flex-row">
            <Link
              href="/auth/login"
              className="inline-flex items-center justify-center rounded-full bg-[#171717] px-7 py-4 text-[14px] font-semibold text-white transition-colors duration-300 hover:bg-black"
              style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}
            >
              Create account
            </Link>
            <Link
              href="/admin/apps"
              className="inline-flex items-center justify-center rounded-full border border-[#171717]/14 px-7 py-4 text-[14px] font-semibold text-[#171717] transition-colors duration-300 hover:bg-[#171717]/4"
              style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}
            >
              See apps
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
}
