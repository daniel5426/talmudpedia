"use client";

import Image from "next/image";
import { useEffect } from "react";
import { useTheme } from "next-themes";

import { AuthAccessProvider, useAuthAccess } from "@/components/auth/auth-access-context";

function AuthShell({ children }: { children: React.ReactNode }) {
  const { registerSecretTap } = useAuthAccess();

  return (
    <div className="flex min-h-svh bg-white">
      <div className="relative hidden lg:block lg:w-1/2">
        <Image
          src="/auth-side.png"
          alt=""
          fill
          priority
          className="absolute inset-0 h-full w-full object-cover"
        />
        <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/60 to-transparent p-10">
          <blockquote className="max-w-sm text-lg font-medium leading-relaxed text-white">
            &ldquo;The best way to predict the future is to create it.&rdquo;
          </blockquote>
          <button
            type="button"
            onClick={registerSecretTap}
            className="mt-3 text-sm text-white/60 transition hover:text-white/90"
          >
            — Peter Drucker
          </button>
        </div>
      </div>

      <div className="flex min-h-svh flex-1 flex-col">
        <div className="border-b border-slate-200 px-6 py-4 lg:hidden">
          <p className="text-sm leading-6 text-slate-500">
            &ldquo;The best way to predict the future is to create it.&rdquo;
          </p>
          <button
            type="button"
            onClick={registerSecretTap}
            className="mt-2 text-xs tracking-[0.2em] text-slate-400 uppercase"
          >
            Peter Drucker
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  const { setTheme } = useTheme();

  useEffect(() => {
    setTheme("light");
  }, [setTheme]);

  return (
    <AuthAccessProvider>
      <AuthShell>{children}</AuthShell>
    </AuthAccessProvider>
  );
}
