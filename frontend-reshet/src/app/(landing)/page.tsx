"use client";

import { useState } from "react";
import { LandingV1 } from "@/components/landing/LandingV1";
import { LandingV2 } from "@/components/landing/LandingV2";
import { LandingV3 } from "@/components/landing/LandingV3";
import { LandingV4 } from "@/components/landing/LandingV4";
import { LandingV5 } from "@/components/landing/LandingV5";

const versions = [
  { id: 1, label: "Dark Minimal", sub: "Linear / Obsidian" },
  { id: 2, label: "Light Editorial", sub: "Cursor" },
  { id: 3, label: "Gradient Mesh", sub: "Vibrant SaaS" },
  { id: 4, label: "Terminal", sub: "Hacker" },
  { id: 5, label: "Bento Grid", sub: "Apple" },
] as const;

const components = {
  1: LandingV1,
  2: LandingV2,
  3: LandingV3,
  4: LandingV4,
  5: LandingV5,
} as const;

export default function HomePage() {
  const [active, setActive] = useState<1 | 2 | 3 | 4 | 5>(1);
  const ActiveComponent = components[active];

  return (
    <>
      {/* Version Selector — fixed bottom bar */}
      <div className="fixed bottom-6 left-1/2 z-[100] -translate-x-1/2">
        <div className="flex items-center gap-1 rounded-full border border-white/10 bg-black/80 p-1.5 shadow-2xl backdrop-blur-xl">
          {versions.map((v) => (
            <button
              key={v.id}
              onClick={() => setActive(v.id as 1 | 2 | 3 | 4 | 5)}
              className={`relative rounded-full px-4 py-2 text-xs font-medium transition-all duration-300 ${
                active === v.id
                  ? "bg-white text-black shadow-lg"
                  : "text-white/60 hover:text-white"
              }`}
            >
              <span className="hidden sm:inline">{v.label}</span>
              <span className="sm:hidden">V{v.id}</span>
              {active === v.id && (
                <span className="mt-0.5 block text-[10px] font-normal opacity-50 hidden sm:block">
                  {v.sub}
                </span>
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Active Landing Page */}
      <ActiveComponent />
    </>
  );
}
