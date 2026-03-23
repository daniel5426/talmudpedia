"use client";

import Link from "next/link";
import {
  ArrowRight,
  BarChart3,
  Braces,
  Database,
  LayoutPanelTop,
  Sparkles,
  Zap,
} from "lucide-react";

const platformPillars = [
  {
    title: "Agent graphs",
    body: "Compose reasoning, tools, retrieval, and guardrails as one deployable system.",
    icon: Braces,
  },
  {
    title: "Knowledge pipelines",
    body: "Turn raw content into retrieval-ready context with operators, stores, and lineage.",
    icon: Database,
  },
  {
    title: "Published apps",
    body: "Ship governed AI products with runtime traces, sessions, and revisions built in.",
    icon: LayoutPanelTop,
  },
] as const;

const journeyEvents = [
  "Run started · pricing-agent-v2",
  "Knowledge hit · 14 passages resolved",
  "Tool call · crm.lookup_customer",
  "Revision published · customer-portal",
] as const;

export function LandingV3() {
  return (
    <div className="relative min-h-screen overflow-hidden bg-[#f5fbf7] text-[#102118] selection:bg-[#1c7c54] selection:text-white">
      <style>{`@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600&family=Sora:wght@400;500;600;700&display=swap');`}</style>

      <div className="pointer-events-none fixed inset-0">
        <div className="absolute left-[-10%] top-[-10%] h-[32rem] w-[32rem] rounded-full bg-[#7af0bc]/25 blur-[120px]" />
        <div className="absolute right-[-8%] top-[16%] h-[28rem] w-[28rem] rounded-full bg-[#d9ff77]/25 blur-[120px]" />
        <div className="absolute bottom-[-14%] left-[18%] h-[26rem] w-[26rem] rounded-full bg-[#8ed6ff]/18 blur-[120px]" />
      </div>

      <nav className="fixed top-0 z-50 w-full">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-5">
          <div className="flex items-center gap-3 rounded-full border border-[#102118]/10 bg-white/80 px-4 py-2 shadow-[0_20px_60px_rgba(16,33,24,0.08)] backdrop-blur-xl">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-[#102118] text-[11px] font-semibold text-white">
              TP
            </div>
            <span
              className="text-[13px] font-semibold tracking-[-0.03em] text-[#102118]"
              style={{ fontFamily: "'Sora', sans-serif" }}
            >
              Talmudpedia
            </span>
          </div>

          <div
            className="hidden items-center gap-8 text-[13px] text-[#102118]/55 md:flex"
            style={{ fontFamily: "'Sora', sans-serif" }}
          >
            <span>Platform</span>
            <span>Customers</span>
            <span>Docs</span>
            <span>Pricing</span>
          </div>

          <Link
            href="/auth/login"
            className="rounded-full bg-[#102118] px-5 py-2.5 text-[13px] font-semibold text-white transition-transform duration-300 hover:-translate-y-0.5"
            style={{ fontFamily: "'Sora', sans-serif" }}
          >
            Start free
          </Link>
        </div>
      </nav>

      <section className="relative px-6 pb-20 pt-32 md:pb-28 md:pt-40">
        <div className="mx-auto grid max-w-7xl gap-12 lg:grid-cols-[1.05fr_0.95fr] lg:items-center">
          <div>
            <div
              className="inline-flex items-center gap-2 rounded-full border border-[#102118]/10 bg-white/80 px-4 py-2 text-[12px] text-[#1c7c54]"
              style={{ fontFamily: "'Sora', sans-serif" }}
            >
              <Sparkles className="h-3.5 w-3.5" />
              Product analytics for agent teams
            </div>

            <h1
              className="mt-7 max-w-[10ch] text-[clamp(3.3rem,8vw,6.6rem)] leading-[0.95] tracking-[-0.06em] text-[#102118]"
              style={{ fontFamily: "'Fraunces', serif" }}
            >
              Turn agent flows into shipped outcomes.
            </h1>

            <p
              className="mt-6 max-w-xl text-[16px] leading-8 text-[#102118]/66 md:text-[17px]"
              style={{ fontFamily: "'Sora', sans-serif" }}
            >
              Talmudpedia unifies agent graphs, knowledge pipelines, runtime traces,
              and published apps so product teams can see what actually creates
              customer value.
            </p>

            <div
              className="mt-8 flex flex-col gap-3 sm:flex-row"
              style={{ fontFamily: "'Sora', sans-serif" }}
            >
              <Link
                href="/auth/login"
                className="group inline-flex items-center justify-center gap-2 rounded-full bg-[#1c7c54] px-7 py-4 text-[14px] font-semibold text-white shadow-[0_24px_50px_rgba(28,124,84,0.24)] transition-all duration-300 hover:-translate-y-0.5 hover:bg-[#176847]"
              >
                Start building
                <ArrowRight className="h-4 w-4 transition-transform duration-300 group-hover:translate-x-1" />
              </Link>
              <Link
                href="/admin/apps"
                className="inline-flex items-center justify-center rounded-full border border-[#102118]/12 bg-white/80 px-7 py-4 text-[14px] font-semibold text-[#102118] backdrop-blur-xl transition-all duration-300 hover:border-[#102118]/24"
              >
                View live demo
              </Link>
            </div>

            <div
              className="mt-10 flex flex-wrap items-center gap-x-8 gap-y-4 text-[11px] uppercase tracking-[0.24em] text-[#102118]/45"
              style={{ fontFamily: "'Sora', sans-serif" }}
            >
              {["RUNTIME TRACES", "APP REVISIONS", "MODEL POLICIES", "TEAM GOVERNANCE"].map((item) => (
                <span key={item}>{item}</span>
              ))}
            </div>
          </div>

          <div>
            <div className="relative rounded-[2rem] border border-white/70 bg-white/85 p-4 shadow-[0_40px_120px_rgba(16,33,24,0.12)] backdrop-blur-2xl">
              <div className="rounded-[1.6rem] border border-[#102118]/8 bg-[#fcfffd] p-5">
                <div
                  className="flex items-center justify-between border-b border-[#102118]/8 pb-4"
                  style={{ fontFamily: "'Sora', sans-serif" }}
                >
                  <div>
                    <p className="text-[11px] uppercase tracking-[0.22em] text-[#102118]/42">
                      Outcome board
                    </p>
                    <p className="mt-1 text-[15px] font-semibold tracking-[-0.03em] text-[#102118]">
                      Growth assistant funnel
                    </p>
                  </div>
                  <div className="rounded-full bg-[#dff8ec] px-3 py-1 text-[11px] font-semibold text-[#1c7c54]">
                    Live
                  </div>
                </div>

                <div className="mt-5 grid gap-3 md:grid-cols-3">
                  {[
                    ["Runs", "18.4K"],
                    ["Qualified answers", "6.9K"],
                    ["Published revisions", "214"],
                  ].map(([label, value]) => (
                    <div key={label} className="rounded-2xl border border-[#102118]/8 bg-[#f7fbf8] p-4">
                      <p
                        className="text-[11px] uppercase tracking-[0.16em] text-[#102118]/45"
                        style={{ fontFamily: "'Sora', sans-serif" }}
                      >
                        {label}
                      </p>
                      <p
                        className="mt-3 text-3xl font-semibold tracking-[-0.05em] text-[#102118]"
                        style={{ fontFamily: "'Fraunces', serif" }}
                      >
                        {value}
                      </p>
                    </div>
                  ))}
                </div>

                <div className="mt-4 grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
                  <div className="rounded-[1.5rem] bg-[#102118] p-5 text-white">
                    <div className="flex items-center justify-between">
                      <div>
                        <p
                          className="text-[11px] uppercase tracking-[0.18em] text-white/55"
                          style={{ fontFamily: "'Sora', sans-serif" }}
                        >
                          Run-to-release
                        </p>
                        <p
                          className="mt-1 text-[22px] tracking-[-0.04em]"
                          style={{ fontFamily: "'Fraunces', serif" }}
                        >
                          38% faster publishing
                        </p>
                      </div>
                      <Zap className="h-5 w-5 text-[#d9ff77]" />
                    </div>
                    <div className="mt-7 flex items-end gap-2">
                      {[38, 54, 49, 72, 80, 91, 88].map((value, index) => (
                        <div key={value} className="flex-1">
                          <div
                            className={`rounded-t-full ${index === 6 ? "bg-[#d9ff77]" : "bg-white/22"}`}
                            style={{ height: `${value}px` }}
                          />
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="rounded-[1.5rem] border border-[#102118]/8 bg-[#f7fbf8] p-5">
                    <div className="flex items-center justify-between">
                      <p
                        className="text-[11px] uppercase tracking-[0.18em] text-[#102118]/45"
                        style={{ fontFamily: "'Sora', sans-serif" }}
                      >
                        Recent signals
                      </p>
                      <BarChart3 className="h-4 w-4 text-[#1c7c54]" />
                    </div>
                    <div className="mt-4 space-y-3">
                      {journeyEvents.map((item, index) => (
                        <div
                          key={item}
                          className="flex items-center gap-3 rounded-2xl bg-white px-4 py-3 shadow-[0_12px_30px_rgba(16,33,24,0.05)]"
                        >
                          <div className="flex h-7 w-7 items-center justify-center rounded-full bg-[#dff8ec] text-[11px] font-semibold text-[#1c7c54]">
                            {index + 1}
                          </div>
                          <span
                            className="text-[13px] text-[#102118]/72"
                            style={{ fontFamily: "'Sora', sans-serif" }}
                          >
                            {item}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="px-6 pb-10">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-5 rounded-[2rem] border border-white/70 bg-white/60 px-6 py-5 text-[13px] text-[#102118]/50 shadow-[0_18px_50px_rgba(16,33,24,0.06)] backdrop-blur-xl">
          {["Sift", "Northstar", "Opal", "Meridian", "Stacked", "Halcyon"].map((name) => (
            <span
              key={name}
              className="font-semibold tracking-[0.18em]"
              style={{ fontFamily: "'Sora', sans-serif" }}
            >
              {name}
            </span>
          ))}
        </div>
      </section>

      <section className="px-6 py-16 md:py-24">
        <div className="mx-auto max-w-7xl">
          <div className="max-w-3xl">
            <p
              className="text-[11px] uppercase tracking-[0.26em] text-[#1c7c54]"
              style={{ fontFamily: "'Sora', sans-serif" }}
            >
              It starts with one platform
            </p>
            <h2
              className="mt-4 text-[clamp(2.5rem,5vw,4.2rem)] leading-[0.98] tracking-[-0.06em] text-[#102118]"
              style={{ fontFamily: "'Fraunces', serif" }}
            >
              No stitched-together AI stack. One operating surface.
            </h2>
          </div>

          <div className="mt-10 grid gap-5 lg:grid-cols-3">
            {platformPillars.map((item) => (
              <div
                key={item.title}
                className="rounded-[2rem] border border-white/75 bg-white/82 p-7 shadow-[0_24px_70px_rgba(16,33,24,0.07)] backdrop-blur-xl"
              >
                <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-[#102118] text-white">
                  <item.icon className="h-5 w-5" />
                </div>
                <h3
                  className="mt-6 text-[24px] tracking-[-0.04em] text-[#102118]"
                  style={{ fontFamily: "'Fraunces', serif" }}
                >
                  {item.title}
                </h3>
                <p
                  className="mt-3 text-[14px] leading-7 text-[#102118]/64"
                  style={{ fontFamily: "'Sora', sans-serif" }}
                >
                  {item.body}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="px-6 pb-24 md:pb-32">
        <div className="mx-auto max-w-7xl rounded-[2.2rem] bg-[#102118] px-8 py-12 text-white md:px-12 md:py-14">
          <div className="grid gap-10 lg:grid-cols-[1fr_auto] lg:items-end">
            <div>
              <p
                className="text-[11px] uppercase tracking-[0.22em] text-white/45"
                style={{ fontFamily: "'Sora', sans-serif" }}
              >
                Ready to measure real platform value?
              </p>
              <h2
                className="mt-4 max-w-2xl text-[clamp(2.4rem,5vw,4.2rem)] leading-[0.98] tracking-[-0.06em]"
                style={{ fontFamily: "'Fraunces', serif" }}
              >
                Build the agent stack your team can actually operate.
              </h2>
            </div>

            <div className="flex flex-col gap-3 sm:flex-row">
              <Link
                href="/auth/login"
                className="inline-flex items-center justify-center rounded-full bg-[#d9ff77] px-7 py-4 text-[14px] font-semibold text-[#102118] transition-colors duration-300 hover:bg-[#cef05d]"
                style={{ fontFamily: "'Sora', sans-serif" }}
              >
                Create account
              </Link>
              <Link
                href="/admin/apps"
                className="inline-flex items-center justify-center rounded-full border border-white/14 px-7 py-4 text-[14px] font-semibold text-white transition-colors duration-300 hover:bg-white/8"
                style={{ fontFamily: "'Sora', sans-serif" }}
              >
                Explore apps
              </Link>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
