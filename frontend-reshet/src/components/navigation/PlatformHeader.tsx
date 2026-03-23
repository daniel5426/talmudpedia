"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Navbar,
  NavBody,
  NavItems,
  MobileNav,
  MobileNavMenu,
  MobileNavToggle,
  MobileNavHeader,
} from "@/components/ui/resizable-navbar";
import { InteractiveHoverButton } from "@/components/ui/interactive-hover-button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useAuthStore } from "@/lib/store/useAuthStore";
import { useState } from "react";

export function PlatformHeader() {
  const [isOpen, setIsOpen] = useState(false);
  const [mounted, setMounted] = useState(false);
  const user = useAuthStore((state) => state.user);
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated());
  const router = useRouter();

  React.useEffect(() => {
    setMounted(true);
  }, []);

  const navItems = [
    { name: "Overview", link: "/" },
    { name: "Apps", link: "/admin/apps" },
    { name: "Agents", link: "/admin/agents" },
  ];

  const getInitial = () => {
    if (user?.full_name) {
      return user.full_name.charAt(0).toUpperCase();
    }
    if (user?.email) {
      return user.email.charAt(0).toUpperCase();
    }
    return "U";
  };

  return (
    <div className="relative w-full">
      <Navbar className="top-4">
        <NavBody className="border border-white/10 bg-white/70 px-5 py-3 text-slate-900 backdrop-blur-xl">
          <Link href="/" className="relative z-30 flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-full border border-slate-200 bg-white text-sm font-semibold uppercase tracking-[0.25em] text-slate-900 shadow-sm">
              TP
            </div>
            <div className="flex flex-col">
              <span className="text-sm font-semibold uppercase tracking-[0.28em] text-slate-500">
                Talmudpedia
              </span>
              <span className="text-sm text-slate-700">Platform</span>
            </div>
          </Link>

          <NavItems
            items={navItems}
            className="text-slate-600 hover:text-slate-900"
          />

          <div className="relative z-30">
            {mounted && isAuthenticated ? (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <button
                    type="button"
                    className="flex h-10 w-10 items-center justify-center rounded-full bg-slate-900 text-sm font-semibold text-white transition-opacity hover:opacity-90"
                  >
                    {getInitial()}
                  </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-48">
                  <DropdownMenuItem
                    onClick={() => router.push("/admin/dashboard")}
                    className="cursor-pointer"
                  >
                    Open dashboard
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    onClick={() => router.push("/chat")}
                    className="cursor-pointer"
                  >
                    Open workspace
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            ) : (
              <Link href="/auth/login">
                <InteractiveHoverButton>Sign in</InteractiveHoverButton>
              </Link>
            )}
          </div>
        </NavBody>

        <MobileNav className="rounded-[28px] border border-white/10 bg-white/80 px-4 py-3 text-slate-900 backdrop-blur-xl">
          <MobileNavHeader>
            <Link href="/" className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-full border border-slate-200 bg-white text-sm font-semibold uppercase tracking-[0.25em] text-slate-900 shadow-sm">
                TP
              </div>
              <div className="flex flex-col">
                <span className="text-xs font-semibold uppercase tracking-[0.28em] text-slate-500">
                  Talmudpedia
                </span>
                <span className="text-sm text-slate-700">Platform</span>
              </div>
            </Link>

            <div className="flex items-center gap-2">
              {mounted && isAuthenticated ? (
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <button
                      type="button"
                      className="flex h-10 w-10 items-center justify-center rounded-full bg-slate-900 text-sm font-semibold text-white transition-opacity hover:opacity-90"
                    >
                      {getInitial()}
                    </button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end" className="w-48">
                    <DropdownMenuItem
                      onClick={() => router.push("/admin/dashboard")}
                      className="cursor-pointer"
                    >
                      Open dashboard
                    </DropdownMenuItem>
                    <DropdownMenuItem
                      onClick={() => router.push("/chat")}
                      className="cursor-pointer"
                    >
                      Open workspace
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              ) : (
                <Link href="/auth/login">
                  <InteractiveHoverButton>Sign in</InteractiveHoverButton>
                </Link>
              )}

              <MobileNavToggle
                isOpen={isOpen}
                onClick={() => setIsOpen(!isOpen)}
              />
            </div>
          </MobileNavHeader>
          <MobileNavMenu isOpen={isOpen} onClose={() => setIsOpen(false)}>
            <div className="flex w-full flex-col gap-4">
              {navItems.map((item) => (
                <Link
                  key={item.link}
                  href={item.link}
                  onClick={() => setIsOpen(false)}
                  className="text-base font-medium text-slate-700"
                >
                  {item.name}
                </Link>
              ))}
            </div>
          </MobileNavMenu>
        </MobileNav>
      </Navbar>
    </div>
  );
}
