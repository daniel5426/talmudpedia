"use client";

import type { ReactNode } from "react";

export default function LandingLayout({
  children,
}: {
  children: ReactNode;
}) {
  return (
    <div className="relative min-h-screen overflow-x-hidden">
      {children}
    </div>
  );
}
