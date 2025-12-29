"use client";

import type { ReactNode } from "react";
import { useEffect } from "react";
import Image from "next/image";
import { KesherHeader } from "@/components/layout/KesherHeader";
import { useDirection } from "@/components/direction-provider";
import { useTheme } from "next-themes";

export default function LandingLayout({
  children,
}: {
  children: ReactNode;
}) {
  const direction = useDirection();
  const { setTheme } = useTheme();

  // Force light theme for landing pages
  useEffect(() => {
    setTheme("light");
  }, [setTheme]);

  return (
    <div dir={direction.direction} className="relative min-h-screen overflow-x-hidden">
      {/* Fixed Background */}
      <div className="fixed inset-0 bg-[linear-gradient(to_bottom_right,#cce4e6,#008E96)] z-[-1]" />

      <div
        dir="ltr"
        className="fixed inset-0 pointer-events-none overflow-visible z-0"
      >
        <Image
          src="/kesher.png"
          alt="Kesher Logo"
          width={1800}
          height={1800}
          className="absolute w-[min(90vw,300px)] md:w-[min(70vw,700px)] opacity-20 -translate-x-[40%] -translate-y-[20%] top-[200px] md:top-[300px]"
          priority
        />
        <Image
          src="/kesher.png"
          alt="Kesher Logo"
          width={1800}
          height={1800}
          className="absolute w-[min(90vw,300px)] md:w-[min(70vw,700px)] opacity-20 translate-x-[40%] translate-y-[50%] right-0"
          priority
        />
        <Image
          src="/kesher.png"
          alt="Kesher Logo"
          width={1800}
          height={1800}
          className="absolute w-[min(50vw,100px)] md:w-[min(70vw,200px)] opacity-90 -translate-x-[80%] translate-y-[60%] right-0 filter brightness-0 invert"
          priority
        />

      </div>
      <div className="relative z-10 flex flex-col min-h-screen">
        <KesherHeader />
        <main className="bg-transparent flex-1">{children}</main>
        {/* Footer */}
        <footer className="relative z-10 w-full py-12 px-4 border-t border-white/10 bg-white/5 backdrop-blur-sm mt-auto">
          <div className="max-w-7xl mx-auto flex flex-col md:flex-row justify-between items-start gap-6">
            <div className="flex flex-col md:items-start">
              <div className="text-2xl font-bold text-white mb-2">רשת</div>
              <p className="text-white/60 text-sm">העתיד של לימוד התורה</p>
            </div>
            <div className="flex gap-3 flex-col text-white/80">
              <div className="text-white font-semibold mb-2">דפים</div>
              <a href="/company" className="hover:text-white transition-colors">החברה</a>
              <a href="/blog" className="hover:text-white transition-colors">בלוג</a>
              <a href="/contact" className="hover:text-white transition-colors">צור קשר</a>
            </div>
            <div className="text-white/40 text-sm">
              © 2024 Kesher AI. All rights reserved.
            </div>
          </div>
        </footer>
      </div>
    </div>
  );
}

