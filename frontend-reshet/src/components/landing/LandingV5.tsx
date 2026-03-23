"use client";

import Link from "next/link";
import {
  ArrowRight,
  Bot,
  ChartNoAxesColumn,
  DatabaseZap,
  LayoutPanelTop,
  MessageCircleMore,
  ShieldCheck,
} from "lucide-react";

const traceCards = [
  {
    title: "Trace every run",
    body: "See graph steps, tool inputs, and knowledge hits in one runtime timeline.",
    icon: ChartNoAxesColumn,
  },
  {
    title: "Ground every answer",
    body: "Connect retrieval pipelines and source context before agents respond.",
    icon: DatabaseZap,
  },
  {
    title: "Publish with control",
    body: "Ship app revisions with explicit governance, rollout history, and audit trails.",
    icon: LayoutPanelTop,
  },
] as const;

const testimonials = [
  {
    quote:
      "Talmudpedia gives our team one place to see how graph changes affect the customer product.",
    author: "NOA K.",
  },
  {
    quote:
      "We moved from scattered prompts and dashboards to one operating surface with real runtime clarity.",
    author: "DANIEL R.",
  },
  {
    quote:
      "The best part is that retrieval, agent behavior, and published apps finally feel connected.",
    author: "MAYA L.",
  },
] as const;

export function LandingV5() {
  return (
    <div className="relative min-h-screen overflow-hidden bg-[#f7faf6] text-[#122018] selection:bg-[#122018] selection:text-white">
      <style>{`@import url('https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,500;6..72,600&family=Urbanist:wght@400;500;600;700;800&display=swap');`}</style>

      <div className="pointer-events-none fixed inset-0">
        <div className="absolute inset-x-0 top-0 h-[28rem] bg-[radial-gradient(circle_at_top,rgba(143,241,176,0.2),transparent_56%)]" />
        <div className="absolute left-[-10%] top-[24%] h-[22rem] w-[22rem] rounded-full bg-[#d8f4d9] blur-[120px]" />
      </div>

      <nav className="fixed top-0 z-50 w-full">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-5">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-full bg-[#122018] text-[11px] font-bold text-white">
              TP
            </div>
            <span
              className="text-[14px] font-semibold tracking-[-0.03em]"
              style={{ fontFamily: "'Urbanist', sans-serif" }}
            >
              Talmudpedia
            </span>
          </div>

          <div
            className="hidden items-center gap-8 text-[13px] text-[#122018]/58 md:flex"
            style={{ fontFamily: "'Urbanist', sans-serif" }}
          >
            <span>Agents</span>
            <span>RAG</span>
            <span>Apps</span>
            <span>Resources</span>
            <span>Company</span>
          </div>

          <div className="flex items-center gap-3">
            <Link
              href="/auth/login"
              className="hidden text-[13px] font-semibold text-[#122018]/60 md:inline-flex"
              style={{ fontFamily: "'Urbanist', sans-serif" }}
            >
              Log in
            </Link>
            <Link
              href="/auth/login"
              className="rounded-full bg-[#122018] px-5 py-2.5 text-[13px] font-semibold text-white transition-transform duration-300 hover:-translate-y-0.5"
              style={{ fontFamily: "'Urbanist', sans-serif" }}
            >
              Get started
            </Link>
          </div>
        </div>
      </nav>

      <section className="px-6 pb-14 pt-32 md:pb-20 md:pt-40">
        <div className="mx-auto max-w-7xl text-center">
          <div>
            <div
              className="inline-flex items-center gap-2 rounded-full border border-[#122018]/10 bg-white/80 px-4 py-2 text-[12px] text-[#2e7d4e] shadow-[0_14px_40px_rgba(18,32,24,0.06)]"
              style={{ fontFamily: "'Urbanist', sans-serif" }}
            >
              New trace explorer is live
            </div>

            <h1
              className="mx-auto mt-6 max-w-[10ch] text-[clamp(3.4rem,7vw,6.2rem)] leading-[0.95] tracking-[-0.06em] text-[#122018]"
              style={{ fontFamily: "'Newsreader', serif" }}
            >
              Own your AI runtime.
            </h1>

            <p
              className="mx-auto mt-6 max-w-2xl text-[17px] leading-8 text-[#122018]/66"
              style={{ fontFamily: "'Urbanist', sans-serif" }}
            >
              Talmudpedia is the all-in-one platform for graph-based agents,
              retrieval pipelines, runtime analytics, and customer-facing AI apps.
            </p>

            <div
              className="mt-8 flex flex-col items-center gap-3 sm:flex-row sm:justify-center"
              style={{ fontFamily: "'Urbanist', sans-serif" }}
            >
              <Link
                href="/auth/login"
                className="group inline-flex items-center justify-center gap-2 rounded-full bg-[#122018] px-7 py-4 text-[14px] font-semibold text-white transition-transform duration-300 hover:-translate-y-0.5"
              >
                Get started
                <ArrowRight className="h-4 w-4 transition-transform duration-300 group-hover:translate-x-1" />
              </Link>
              <Link
                href="/admin/apps"
                className="inline-flex items-center justify-center rounded-full border border-[#122018]/12 bg-white/75 px-7 py-4 text-[14px] font-semibold text-[#122018] transition-colors duration-300 hover:border-[#122018]/24"
              >
                Explore apps
              </Link>
            </div>
          </div>

          <div className="mx-auto mt-12 max-w-5xl rounded-[2.4rem] border border-white/80 bg-white/82 p-5 shadow-[0_28px_90px_rgba(18,32,24,0.08)] backdrop-blur-2xl">
            <div className="rounded-[2rem] border border-[#122018]/8 bg-[#fbfdfb] p-5 md:p-7">
              <div className="grid gap-5 lg:grid-cols-[1.15fr_0.85fr]">
                <div className="rounded-[1.8rem] bg-[#122018] p-6 text-white">
                  <div className="flex items-center justify-between">
                    <div>
                      <p
                        className="text-[11px] uppercase tracking-[0.2em] text-white/45"
                        style={{ fontFamily: "'Urbanist', sans-serif" }}
                      >
                        Track everything
                      </p>
                      <p
                        className="mt-2 text-[30px] leading-[1.02] tracking-[-0.05em]"
                        style={{ fontFamily: "'Newsreader', serif" }}
                      >
                        Trace every graph, tool call, and release.
                      </p>
                    </div>
                    <ChartNoAxesColumn className="h-5 w-5 text-[#9cf2aa]" />
                  </div>

                  <div className="mt-8 grid gap-3 sm:grid-cols-3">
                    {[
                      ["Runs", "18.4K"],
                      ["Tool calls", "52.1K"],
                      ["Published revisions", "214"],
                    ].map(([label, value]) => (
                      <div key={label} className="rounded-2xl bg-white/8 p-4">
                        <p className="text-[11px] uppercase tracking-[0.16em] text-white/42">
                          {label}
                        </p>
                        <p
                          className="mt-3 text-[28px] tracking-[-0.05em]"
                          style={{ fontFamily: "'Newsreader', serif" }}
                        >
                          {value}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="space-y-4">
                  {[
                    "Graph compile completed",
                    "Knowledge hit resolved 14 passages",
                    "Tool call crm.lookup_customer succeeded",
                    "App revision published to production",
                  ].map((item) => (
                    <div
                      key={item}
                      className="rounded-[1.4rem] bg-[#f3f8f2] px-4 py-4 text-left text-[13px] text-[#122018]/72"
                      style={{ fontFamily: "'Urbanist', sans-serif" }}
                    >
                      {item}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="px-6 py-14 md:py-20">
        <div className="mx-auto max-w-7xl">
          <div className="text-center">
            <p
              className="text-[11px] uppercase tracking-[0.26em] text-[#2e7d4e]"
              style={{ fontFamily: "'Urbanist', sans-serif" }}
            >
              Build everything. Ask anything.
            </p>
          </div>

          <div className="mt-10 grid gap-5 lg:grid-cols-[0.85fr_1.15fr]">
            <div className="rounded-[2.2rem] bg-white/82 p-7 shadow-[0_24px_80px_rgba(18,32,24,0.06)] backdrop-blur-xl">
              <p
                className="text-[11px] uppercase tracking-[0.2em] text-[#122018]/42"
                style={{ fontFamily: "'Urbanist', sans-serif" }}
              >
                Ask anything
              </p>
              <h2
                className="mt-4 text-[clamp(2.2rem,5vw,3.9rem)] leading-[0.98] tracking-[-0.05em] text-[#122018]"
                style={{ fontFamily: "'Newsreader', serif" }}
              >
                Ask your platform what happened and why.
              </h2>
              <p
                className="mt-4 text-[15px] leading-8 text-[#122018]/66"
                style={{ fontFamily: "'Urbanist', sans-serif" }}
              >
                Talmudpedia turns runtime history into grounded answers, with
                retrieval context, tool outputs, and product state already in view.
              </p>
            </div>

            <div className="rounded-[2.2rem] bg-[#122018] p-7 text-white">
              <div className="flex items-center gap-2 text-[12px] text-white/46">
                <Bot className="h-4 w-4 text-[#9cf2aa]" />
                AI operator console
              </div>
              <div className="mt-5 space-y-4">
                {[
                  {
                    q: "Why did conversion drop after revision 12?",
                    a: "The new graph branch increased tool latency and reduced guided session completion by 11%.",
                  },
                  {
                    q: "Which knowledge store is driving the best outcomes?",
                    a: "The support-corpus store contributes to 38% of successful resolutions with the highest citation confidence.",
                  },
                ].map((item) => (
                  <div key={item.q} className="rounded-[1.6rem] bg-white/8 p-5">
                    <div className="flex items-start gap-3">
                      <MessageCircleMore className="mt-1 h-4 w-4 text-[#9cf2aa]" />
                      <div>
                        <p
                          className="text-[14px] font-semibold text-white"
                          style={{ fontFamily: "'Urbanist', sans-serif" }}
                        >
                          {item.q}
                        </p>
                        <p
                          className="mt-2 text-[13px] leading-7 text-white/66"
                          style={{ fontFamily: "'Urbanist', sans-serif" }}
                        >
                          {item.a}
                        </p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="px-6 py-14 md:py-20">
        <div className="mx-auto max-w-7xl">
          <div className="grid gap-5 lg:grid-cols-[1.05fr_0.95fr]">
            <div className="rounded-[2.2rem] bg-white/82 p-7 shadow-[0_24px_80px_rgba(18,32,24,0.06)] backdrop-blur-xl">
              <p
                className="text-[11px] uppercase tracking-[0.2em] text-[#122018]/42"
                style={{ fontFamily: "'Urbanist', sans-serif" }}
              >
                Ship your product
              </p>
              <h2
                className="mt-4 text-[clamp(2.2rem,5vw,3.9rem)] leading-[0.98] tracking-[-0.05em] text-[#122018]"
                style={{ fontFamily: "'Newsreader', serif" }}
              >
                Publish AI apps with real operating discipline.
              </h2>
              <p
                className="mt-4 text-[15px] leading-8 text-[#122018]/66"
                style={{ fontFamily: "'Urbanist', sans-serif" }}
              >
                Revision history, scoped access, embedded runtimes, and controlled
                rollout paths are built in before your first customer sees the app.
              </p>
            </div>

            <div className="grid gap-4 sm:grid-cols-3">
              {traceCards.map((card) => (
                <div
                  key={card.title}
                  className="rounded-[1.8rem] border border-[#122018]/8 bg-[#f2f7f1] p-5"
                >
                  <div className="flex h-11 w-11 items-center justify-center rounded-full bg-[#122018] text-white">
                    <card.icon className="h-4 w-4" />
                  </div>
                  <h3
                    className="mt-5 text-[24px] leading-[1.02] tracking-[-0.04em] text-[#122018]"
                    style={{ fontFamily: "'Newsreader', serif" }}
                  >
                    {card.title}
                  </h3>
                  <p
                    className="mt-3 text-[14px] leading-7 text-[#122018]/64"
                    style={{ fontFamily: "'Urbanist', sans-serif" }}
                  >
                    {card.body}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className="px-6 py-14 md:py-20">
        <div className="mx-auto max-w-7xl">
          <div className="rounded-[2.4rem] bg-[#ecf7ec] px-8 py-10">
            <p
              className="text-center text-[11px] uppercase tracking-[0.24em] text-[#2e7d4e]"
              style={{ fontFamily: "'Urbanist', sans-serif" }}
            >
              Read what teams say
            </p>

            <div className="mt-8 grid gap-4 md:grid-cols-3">
              {testimonials.map((item) => (
                <div key={item.author} className="rounded-[1.8rem] bg-white p-6 shadow-[0_18px_50px_rgba(18,32,24,0.05)]">
                  <div className="flex items-center gap-1 text-[#2e7d4e]">
                    {Array.from({ length: 5 }).map((_, index) => (
                      <ShieldCheck key={index} className="h-4 w-4" />
                    ))}
                  </div>
                  <p
                    className="mt-5 text-[15px] leading-8 text-[#122018]/74"
                    style={{ fontFamily: "'Urbanist', sans-serif" }}
                  >
                    {item.quote}
                  </p>
                  <p
                    className="mt-5 text-[12px] font-bold tracking-[0.2em] text-[#122018]/48"
                    style={{ fontFamily: "'Urbanist', sans-serif" }}
                  >
                    {item.author}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className="px-6 pb-24 pt-8 md:pb-32">
        <div className="mx-auto max-w-7xl rounded-[2.4rem] bg-[#122018] px-8 py-10 text-center text-white md:px-12 md:py-12">
          <p
            className="text-[11px] uppercase tracking-[0.22em] text-white/44"
            style={{ fontFamily: "'Urbanist', sans-serif" }}
          >
            Ready to deploy?
          </p>
          <h2
            className="mx-auto mt-4 max-w-[10ch] text-[clamp(2.5rem,5vw,4.2rem)] leading-[0.98] tracking-[-0.05em]"
            style={{ fontFamily: "'Newsreader', serif" }}
          >
            Download the stack your AI team actually needs.
          </h2>
          <p
            className="mx-auto mt-4 max-w-xl text-[15px] leading-8 text-white/66"
            style={{ fontFamily: "'Urbanist', sans-serif" }}
          >
            Start with agent graphs, keep the runtime visible, and ship apps with
            the controls buyers expect.
          </p>
          <div
            className="mt-8 flex flex-col items-center gap-3 sm:flex-row sm:justify-center"
            style={{ fontFamily: "'Urbanist', sans-serif" }}
          >
            <Link
              href="/auth/login"
              className="inline-flex items-center justify-center rounded-full bg-[#9cf2aa] px-7 py-4 text-[14px] font-semibold text-[#122018] transition-colors duration-300 hover:bg-[#89e499]"
            >
              Get started
            </Link>
            <Link
              href="/admin/apps"
              className="inline-flex items-center justify-center rounded-full border border-white/14 px-7 py-4 text-[14px] font-semibold text-white transition-colors duration-300 hover:bg-white/8"
            >
              Explore platform
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
}
