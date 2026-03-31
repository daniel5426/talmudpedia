"use client";

import { useState } from "react";
import { Cpu, Globe, Bot } from "lucide-react";

const screenshots = {
  builder: "/platform_screenshot/Screenshot 2026-03-23 at 22.58.34.png",
  stats: "/platform_screenshot/Screenshot 2026-03-23 at 22.49.30.png",
  artifacts: "/platform_screenshot/Screenshot 2026-03-23 at 22.50.52.png",
  dashboard: "/platform_screenshot/Screenshot 2026-03-23 at 22.49.10.png",
  agents: "/platform_screenshot/Screenshot 2026-03-23 at 22.59.00.png",
  apps: "/platform_screenshot/Screenshot 2026-03-23 at 23.00.26.png",
};

/* ──────────────────────────────────────────────────────────
   Expandable Features Large (features-16 style)
   Split header, large container with screenshot, bottom tabs
   ────────────────────────────────────────────────────────── */

const largeTabs = [
  {
    id: "builder",
    label: "Agent Builder",
    screenshot: screenshots.builder,
    desc: "Design multi-step reasoning graphs with drag-and-drop composition. Each agent version is tracked and deployable with one click.",
  },
  {
    id: "analytics",
    label: "Analytics",
    screenshot: screenshots.stats,
    desc: "Track usage, spend, agent performance, and pipeline health from a single analytics surface in real time.",
  },
  {
    id: "artifacts",
    label: "Code Artifacts",
    screenshot: screenshots.artifacts,
    desc: "Write Python functions, tool integrations, and custom workers directly in the platform. Each artifact is versioned and testable.",
  },
];

export function ExpandableFeaturesLarge() {
  const [activeTab, setActiveTab] = useState("builder");
  const active = largeTabs.find((t) => t.id === activeTab)!;

  return (
    <section className="py-20 md:py-28 px-6">
      <div className="max-w-6xl mx-auto">
        <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-6 mb-12">
          <h2 className="text-3xl md:text-[40px] font-semibold tracking-tight text-gray-900 leading-[1.15] max-w-md">
            Ship with confidence
            <br />
            using our unified platform
          </h2>
          <p className="text-base text-gray-500 max-w-sm leading-relaxed md:pt-2">
            Streamline your workflow with tools designed to enhance productivity
            at every step.
          </p>
        </div>

        <div className="rounded-3xl bg-gradient-to-br from-stone-100 via-stone-50 to-amber-50/30 border border-gray-200/50 p-3 md:p-5">
          <div className="rounded-2xl bg-white shadow-sm border border-gray-200/40 overflow-hidden">
            <img
              src={active.screenshot}
              alt={active.label}
              className="w-full block min-h-[260px] md:min-h-[420px] object-cover object-top"
              loading="lazy"
            />
          </div>
        </div>

        <div className="mt-8 flex items-center gap-6">
          {largeTabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`text-sm pb-1 transition-all duration-200 ${
                activeTab === tab.id
                  ? "text-gray-900 font-semibold"
                  : "text-gray-400 hover:text-gray-600 font-medium"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <p className="mt-4 text-base text-gray-500 max-w-xl leading-relaxed">
          {active.desc}
        </p>
      </div>
    </section>
  );
}

/* ──────────────────────────────────────────────────────────
   Expandable Features Vertical (features-5 style)
   Dark slate container with floating screenshot,
   white tab panel overlapping bottom-left corner
   ────────────────────────────────────────────────────────── */

const verticalTabs = [
  {
    id: "models",
    label: "AI Models",
    icon: Cpu,
    screenshot: screenshots.dashboard,
  },
  {
    id: "deploy",
    label: "Global Reach",
    icon: Globe,
    screenshot: screenshots.agents,
  },
  {
    id: "agents",
    label: "Smart Agent",
    icon: Bot,
    screenshot: screenshots.apps,
  },
];

export function ExpandableFeaturesVertical() {
  const [activeTab, setActiveTab] = useState("models");
  const active = verticalTabs.find((t) => t.id === activeTab)!;

  return (
    <section className="py-20 md:py-28 px-6">
      <div className="max-w-6xl mx-auto">
        <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-6 mb-12">
          <h2 className="text-3xl md:text-[40px] font-semibold tracking-tight text-gray-900 leading-[1.15] max-w-md">
            Deploy anywhere,
            <br />
            scale effortlessly
          </h2>
          <p className="text-base text-gray-500 max-w-sm leading-relaxed md:pt-2">
            Multi-model AI routing with global edge deployment and intelligent
            agent orchestration.
          </p>
        </div>

        {/* Main layout */}
        <div className="relative">
          {/* Dark container */}
          <div className="rounded-[32px] bg-gradient-to-br from-[#4a5568] to-[#2d3748] overflow-hidden">
            {/* Mobile tabs — horizontal, inside the dark container */}
            <div className="flex gap-2 px-6 pt-6 md:hidden">
              {verticalTabs.map((tab) => {
                const Icon = tab.icon;
                const isActive = activeTab === tab.id;
                return (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id)}
                    className={`flex items-center gap-2 px-3 py-2 rounded-xl text-xs font-medium transition-all ${
                      isActive
                        ? "bg-white text-gray-900"
                        : "text-white/60 hover:text-white/80"
                    }`}
                  >
                    <Icon className="w-3.5 h-3.5" />
                    {tab.label}
                  </button>
                );
              })}
            </div>

            {/* Screenshot — with left padding on desktop for tab panel */}
            <div className="p-6 pb-24 md:p-10 md:pb-10 md:pl-44 lg:pl-48">
              <div className="rounded-2xl overflow-hidden shadow-[0_25px_60px_-15px_rgba(0,0,0,0.4)] min-h-[260px] md:min-h-[460px]">
                <img
                  src={active.screenshot}
                  alt={active.label}
                  className="w-full h-full block object-cover object-top"
                  loading="lazy"
                />
              </div>
            </div>
          </div>

          {/* White tab panel — overlapping bottom-left, blends with page bg */}
          <div className="hidden md:block absolute bottom-0 left-0 bg-white rounded-tr-[28px] px-8 pt-8 pb-6 z-10">
            <div className="flex flex-col gap-5">
              {verticalTabs.map((tab) => {
                const Icon = tab.icon;
                const isActive = activeTab === tab.id;
                return (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id)}
                    className={`flex items-center gap-3 text-sm font-medium transition-all duration-200 ${
                      isActive
                        ? "text-gray-900"
                        : "text-gray-400 hover:text-gray-600"
                    }`}
                  >
                    <Icon className="w-[18px] h-[18px]" />
                    {tab.label}
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
