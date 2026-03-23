"use client";

import { useState } from "react";
import { LandingV9 } from "@/components/landing/LandingV9";
import { LandingV10 } from "@/components/landing/LandingV10";
import { LandingV11 } from "@/components/landing/LandingV11";
import { LandingV12 } from "@/components/landing/LandingV12";

const versions = [
  { id: 1, label: "Dashboard", sub: "Platform Overview" },
  { id: 2, label: "Agents", sub: "Agent Catalog" },
  { id: 3, label: "Builder", sub: "Developer-First" },
  { id: 4, label: "Analytics", sub: "Governance" },
] as const;

const components = {
  1: LandingV9,
  2: LandingV10,
  3: LandingV11,
  4: LandingV12,
} as const;

export default function HomePage() {
  const [active, setActive] = useState<1 | 2 | 3 | 4>(1);
  const ActiveComponent = components[active];

  return (
    <>
      <div className="fixed bottom-6 left-1/2 z-[100] -translate-x-1/2">
        <div className="flex items-center gap-1 rounded-full border border-white/10 bg-black/80 p-1.5 shadow-2xl backdrop-blur-xl">
          {versions.map((v) => (
            <button
              key={v.id}
              onClick={() => setActive(v.id as 1 | 2 | 3 | 4)}
              className={`relative rounded-full px-4 py-2 text-xs font-medium transition-all duration-300 ${
                active === v.id
                  ? "bg-white text-black shadow-lg"
                  : "text-white/60 hover:text-white"
              }`}
            >
              <span className="hidden md:inline">{v.label}</span>
              <span className="md:hidden">V{v.id}</span>
              {active === v.id && (
                <span className="mt-0.5 block text-[10px] font-normal opacity-50 hidden sm:block">
                  {v.sub}
                </span>
              )}
            </button>
          ))}
        </div>
      </div>
      <ActiveComponent />
    </>
  );
}
