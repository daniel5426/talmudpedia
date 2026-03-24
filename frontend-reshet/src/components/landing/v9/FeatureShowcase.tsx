"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { Zap, Shield, BarChart3 } from "lucide-react";

/* ──────────────────────────────────────────────────────────
   Expandable Features Cards (features-3 style)
   3 clickable cards — active expands, auto-cycles with progress bar
   ────────────────────────────────────────────────────────── */

const CYCLE_DURATION = 5000;

const featureCards = [
  {
    id: "workflow",
    titleBold: "Agent orchestration",
    desc: "with AI-powered graph building, version control, and seamless collaboration for faster deployment.",
  },
  {
    id: "analytics",
    titleBold: "Real-time analytics",
    desc: "tracking usage, cost, and agent performance from a single dashboard in real time.",
  },
  {
    id: "models",
    titleBold: "Multi-model routing",
    desc: "intelligent routing across providers with automatic fallback and cost optimization.",
  },
];

function WorkflowOverlay() {
  return (
    <div className="absolute inset-0 flex flex-col items-center justify-center gap-2.5 p-6">
      {[
        { icon: "\u2705", text: "Workflow completed", time: "" },
        { icon: "\uD83D\uDD17", text: "Issue created", time: "12s ago" },
        { icon: "\u26A1", text: "Branch created", time: "3s ago" },
        { icon: "\u25B2", text: "Preview deployed", time: "now" },
      ].map((item, i) => (
        <div
          key={i}
          className="flex items-center gap-2.5 bg-white rounded-xl px-4 py-2.5 shadow-sm border border-gray-100 text-sm"
          style={{ marginLeft: `${i * 16}px` }}
        >
          <span>{item.icon}</span>
          <span className="font-medium text-gray-900">{item.text}</span>
          {item.time && (
            <span className="text-gray-400 text-xs">{item.time}</span>
          )}
        </div>
      ))}
    </div>
  );
}

function AnalyticsOverlay() {
  return (
    <div className="absolute inset-0 flex items-center justify-center p-6">
      <div className="relative">
        <div className="grid grid-cols-8 gap-2">
          {Array.from({ length: 48 }).map((_, i) => (
            <div
              key={i}
              className={`w-2.5 h-2.5 rounded-full ${
                [21, 28, 35].includes(i) ? "bg-gray-400" : "bg-gray-200"
              }`}
            />
          ))}
        </div>
        <div className="absolute top-[52px] left-[48px] w-8 h-8 rounded-full bg-amber-100 border-2 border-white shadow-sm flex items-center justify-center text-sm">
          \uD83D\uDE00
        </div>
      </div>
    </div>
  );
}

function ModelsOverlay() {
  return (
    <div className="absolute inset-0 flex flex-col items-end justify-center gap-3 p-6 pr-8">
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden w-48">
        {[
          { name: "Gemini", count: "2x" },
          { name: "Open AI", count: "5x" },
          { name: "Deepseek", count: "3x" },
          { name: "Mistral AI", count: "4x" },
          { name: "Qwen", count: "6x" },
        ].map((m, i) => (
          <div
            key={i}
            className="flex items-center justify-between px-4 py-2 text-sm border-b border-gray-50 last:border-0"
          >
            <span className="text-gray-700 font-medium">{m.name}</span>
            <span className="text-gray-400 text-xs">{m.count}</span>
          </div>
        ))}
      </div>
      <div className="flex items-center gap-2 bg-white rounded-xl px-4 py-2.5 shadow-sm border border-gray-100 text-sm">
        <span className="text-gray-400">&infin;</span>
        <span className="font-medium text-gray-900">Agent</span>
        <span className="text-gray-600">Claude Opus 4.5</span>
        <span className="text-gray-400">&or;</span>
      </div>
    </div>
  );
}

const overlays: Record<string, () => React.JSX.Element> = {
  workflow: WorkflowOverlay,
  analytics: AnalyticsOverlay,
  models: ModelsOverlay,
};

export function ExpandableFeaturesCards() {
  const [activeIndex, setActiveIndex] = useState(0);
  const [animKey, setAnimKey] = useState(0);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const goToCard = useCallback((index: number) => {
    setActiveIndex(index);
    setAnimKey((k) => k + 1);
  }, []);

  // Auto-advance after CYCLE_DURATION
  useEffect(() => {
    timeoutRef.current = setTimeout(() => {
      goToCard((activeIndex + 1) % featureCards.length);
    }, CYCLE_DURATION);
    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, [activeIndex, animKey, goToCard]);

  return (
    <section className="py-20 md:py-28 px-6">
      <style>{`
        @keyframes progressFill {
          from { transform: scaleX(0); }
          to { transform: scaleX(1); }
        }
      `}</style>
      <div className="max-w-5xl mx-auto">
        <h2 className="text-3xl md:text-[40px] font-semibold tracking-tight text-gray-900 leading-[1.15] mb-12 max-w-md">
          Powerful features
          <br />
          for modern teams
        </h2>

        {/* Expandable cards */}
        <div className="flex gap-4">
          {featureCards.map((card, i) => {
            const isActive = i === activeIndex;
            const Overlay = overlays[card.id];
            return (
              <div
                key={card.id}
                onClick={() => goToCard(i)}
                className={`cursor-pointer transition-all duration-700 ease-[cubic-bezier(0.16,1,0.3,1)] min-w-0 ${
                  isActive ? "flex-[2]" : "flex-[1]"
                }`}
              >
                <div className="relative rounded-2xl bg-gradient-to-br from-stone-100 via-stone-50 to-amber-50/20 border border-gray-200/50 overflow-hidden aspect-[4/3]">
                  <Overlay />
                </div>
              </div>
            );
          })}
        </div>

        {/* Progress bar — segmented, matching card widths */}
        <div className="mt-6 flex gap-4">
          {featureCards.map((_, i) => (
            <div
              key={i}
              className={`h-[3px] rounded-full bg-gray-100 overflow-hidden transition-all duration-700 ease-[cubic-bezier(0.16,1,0.3,1)] ${
                i === activeIndex ? "flex-[2]" : "flex-[1]"
              }`}
            >
              {i === activeIndex ? (
                <div
                  key={animKey}
                  className="h-full bg-gray-900 rounded-full origin-left"
                  style={{
                    animation: `progressFill ${CYCLE_DURATION}ms linear forwards`,
                  }}
                />
              ) : null}
            </div>
          ))}
        </div>

        {/* Descriptions — widths match cards */}
        <div className="mt-5 flex gap-4">
          {featureCards.map((card, i) => (
            <div
              key={card.id}
              className={`transition-all duration-700 ease-[cubic-bezier(0.16,1,0.3,1)] min-w-0 ${
                i === activeIndex ? "flex-[2]" : "flex-[1]"
              }`}
            >
              <p className="text-sm text-gray-900 leading-relaxed">
                <span className="font-semibold">{card.titleBold}</span>
                {card.desc && (
                  <span className="text-gray-500"> {card.desc}</span>
                )}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ──────────────────────────────────────────────────────────
   Features Code (features-7 style)
   Code editor window with tabs + 3 feature cards below
   ────────────────────────────────────────────────────────── */

const codeTabs = [
  { id: "python", label: "Python", icon: "\uD83D\uDC0D" },
  { id: "typescript", label: "TypeScript", icon: "\uD83D\uDCD8" },
  { id: "curl", label: "cURL", icon: "\u26A1" },
  { id: "go", label: "Go", icon: "\uD83D\uDD37" },
];

const codeSnippets: Record<string, string[]> = {
  python: [
    'from agents24 import Client',
    '',
    'client = Client(api_key="sk_...")',
    '',
    'result = await client.agents.run(',
    '    agent_id="ag_invoice_processor",',
    '    input="Process Q4 invoices",',
    '    stream=True',
    ')',
    '',
    'async for chunk in result:',
    '    print(chunk.text, end="")',
  ],
  typescript: [
    'import { Agents24 } from "@agents24/sdk";',
    '',
    'const client = new Agents24({',
    '  apiKey: "sk_..."',
    '});',
    '',
    'const stream = await client.agents.run({',
    '  agentId: "ag_invoice_processor",',
    '  input: "Process Q4 invoices",',
    '});',
    '',
    'for await (const chunk of stream) {',
    '  process.stdout.write(chunk.text);',
    '}',
  ],
  curl: [
    'curl -X POST https://api.agents24.ai/v1/agents/run \\',
    '  -H "Authorization: Bearer sk_..." \\',
    '  -H "Content-Type: application/json" \\',
    '  -d \'{',
    '    "agent_id": "ag_invoice_processor",',
    '    "input": "Process Q4 invoices",',
    '    "stream": true',
    '  }\'',
  ],
  go: [
    'import "github.com/agents24/agents24-go"',
    '',
    'client := agents24.NewClient("sk_...")',
    '',
    'stream, err := client.Agents.Run(ctx,',
    '  agents24.RunParams{',
    '    AgentID: "ag_invoice_processor",',
    '    Input:   "Process Q4 invoices",',
    '    Stream:  true,',
    '  },',
    ')',
  ],
};

const codeFeatures = [
  {
    icon: Zap,
    title: "Sub-100ms Latency",
    desc: "Edge-optimized inference with intelligent model routing for blazing fast responses.",
  },
  {
    icon: Shield,
    title: "End-to-End Encryption",
    desc: "SOC 2 compliant with full data encryption at rest and in transit across all endpoints.",
  },
  {
    icon: BarChart3,
    title: "Infinite Scale",
    desc: "Auto-scaling infrastructure that handles millions of agent runs without configuration.",
  },
];

export function FeaturesCode() {
  const [activeCodeTab, setActiveCodeTab] = useState("python");

  return (
    <section className="py-20 md:py-28 px-6">
      <div className="max-w-4xl mx-auto">
        {/* Code window */}
        <div className="rounded-2xl border border-gray-200/80 bg-white shadow-sm overflow-hidden">
          {/* Window chrome */}
          <div className="flex items-center gap-4 px-5 py-3 border-b border-gray-100">
            <div className="flex gap-1.5">
              <div className="w-3 h-3 rounded-full bg-gray-200" />
              <div className="w-3 h-3 rounded-full bg-gray-200" />
              <div className="w-3 h-3 rounded-full bg-gray-200" />
            </div>
            <div className="flex items-center gap-1">
              {codeTabs.map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setActiveCodeTab(tab.id)}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                    activeCodeTab === tab.id
                      ? "bg-gray-100 text-gray-900"
                      : "text-gray-400 hover:text-gray-600"
                  }`}
                >
                  <span className="text-sm">{tab.icon}</span>
                  {tab.label}
                </button>
              ))}
            </div>
          </div>

          {/* Code content */}
          <div className="p-6 font-mono text-[13px] leading-[1.9]">
            {(codeSnippets[activeCodeTab] || []).map((line, i) => (
              <div key={i} className="flex">
                <span className="w-8 shrink-0 text-right pr-4 text-gray-300 select-none">
                  {i + 1}
                </span>
                <span className="text-gray-700">{line}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Feature cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mt-10">
          {codeFeatures.map((feat) => {
            const Icon = feat.icon;
            return (
              <div key={feat.title}>
                <div className="w-8 h-8 rounded-lg bg-gray-50 border border-gray-100 flex items-center justify-center mb-3">
                  <Icon className="w-4 h-4 text-gray-500" />
                </div>
                <h3 className="text-sm font-semibold text-gray-900 mb-1">
                  {feat.title}
                </h3>
                <p className="text-sm text-gray-500 leading-relaxed">
                  {feat.desc}
                </p>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
