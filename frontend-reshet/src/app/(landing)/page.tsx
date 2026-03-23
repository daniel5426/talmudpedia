"use client";

import { useState } from "react";
import { LandingV6 } from "@/components/landing/LandingV6";
import { LandingV7 } from "@/components/landing/LandingV7";
import { LandingV8 } from "@/components/landing/LandingV8";

const versions = [
  { id: 1, label: "Dub Replica", sub: "Dub / Original" },
  { id: 2, label: "ObsidianOS", sub: "Obsidian / Original" },
  { id: 3, label: "Talmudpedia", sub: "Original Synthesis" },
] as const;

const components = {
  1: LandingV6,
  2: LandingV7,
  3: LandingV8,
} as const;

export default function HomePage() {
  const [active, setActive] = useState<1 | 2 | 3>(3);
  const ActiveComponent = components[active];

  return (
    <>
      <div className="fixed bottom-6 left-1/2 z-[100] -translate-x-1/2">
        <div className="flex items-center gap-1 rounded-full border border-white/10 bg-black/80 p-1.5 shadow-2xl backdrop-blur-xl">
          {versions.map((v) => (
            <button
              key={v.id}
              onClick={() => setActive(v.id as 1 | 2 | 3)}
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
