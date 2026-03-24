"use client";

import { useEffect } from "react";
import { useTheme } from "next-themes";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  const { setTheme } = useTheme();

  useEffect(() => {
    setTheme("light");
  }, [setTheme]);

  return (
    <div className="flex min-h-svh bg-white">
      {/* Left — Image panel */}
      <div className="relative hidden lg:block lg:w-1/2">
        <img
          src="/auth-side.png"
          alt=""
          className="absolute inset-0 w-full h-full object-cover"
        />
        {/* Quote overlay */}
        <div className="absolute bottom-0 left-0 right-0 p-10 bg-gradient-to-t from-black/60 to-transparent">
          <blockquote className="text-white text-lg font-medium leading-relaxed max-w-sm">
            &ldquo;The best way to predict the future is to create it.&rdquo;
          </blockquote>
          <p className="text-white/60 text-sm mt-3">— Peter Drucker</p>
        </div>
      </div>

      {/* Right — Form panel */}
      <div className="flex flex-1 flex-col min-h-svh">
        {children}
      </div>
    </div>
  );
}
