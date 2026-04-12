"use client";

import type { ReactNode } from "react";
import { LandingHeader } from "@/components/marketing/landing-header";
import { useHeaderStore } from "@/lib/store/useHeaderStore";

export default function LandingLayout({
  children,
}: {
  children: ReactNode;
}) {
  const { scrolled, onSelectDomain } = useHeaderStore();

  return (
    <div className="relative min-h-screen overflow-x-hidden">
      <LandingHeader 
        scrolled={scrolled} 
        onSelectDomain={onSelectDomain ?? undefined} 
      />
      {children}
    </div>
  );
}
