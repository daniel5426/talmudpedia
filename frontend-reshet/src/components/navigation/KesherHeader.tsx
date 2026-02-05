"use client";

import * as React from "react";
import Image from "next/image";
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

export function KesherHeader() {
  const [isOpen, setIsOpen] = useState(false);
  const [mounted, setMounted] = useState(false);
  const user = useAuthStore((state) => state.user);
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated());
  const router = useRouter();

  // Prevent hydration mismatch by only showing auth state after mount
  React.useEffect(() => {
    setMounted(true);
  }, []);

  const navItems = [
    { name: "בית", link: "/" },
    { name: "צ'אט", link: "/chat" },
    { name: "החברה", link: "/company" },
    { name: "בלוג", link: "/blog" },
    { name: "צור קשר", link: "/contact" },
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
        <NavBody>
          {/* Logo and Title - Left side */}
          <div className="flex items-center gap-2 relative z-30">
            <Link href="/" className="relative h-10 w-10">
              <Image
                src="/kesher.png"
                alt="Kesher Logo"
                fill
                className="object-contain"
              />
            </Link>
            <span className="text-2xl font-bold">רשת</span>
          </div>

          <NavItems items={navItems} />

          {/* Auth Section - Right side */}
          <div className="relative z-30">
            {mounted && isAuthenticated ? (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <button 
                    type="button"
                    className="flex h-10 w-10 items-center justify-center rounded-full bg-primary text-primary-foreground font-semibold hover:opacity-90 transition-opacity cursor-pointer"
                  >
                    {getInitial()}
                  </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="start" className="w-48">
                  <DropdownMenuItem dir="rtl"
                    onClick={() => router.push("/chat")}
                    className="cursor-pointer"
                  >
                    התחל לשוחח
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            ) : (
              <Link href="/auth/login">
                <InteractiveHoverButton>התחבר</InteractiveHoverButton>
              </Link>
            )}
          </div>
        </NavBody>

        <MobileNav>
          <MobileNavHeader>
            {/* Logo and Title - Left side */}
            <div className="flex items-center gap-2">
              <Link href="/" className="relative h-10 w-10">
                <Image
                  src="/kesher.png"
                  alt="Kesher Logo"
                  fill
                  className="object-contain"
                />
              </Link>
              <span className="text-2xl font-bold">רשת</span>
            </div>

            {/* Right side controls */}
            <div className="flex items-center gap-2">
              {/* Auth Section - Mobile */}
              {mounted && isAuthenticated ? (
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <button 
                      type="button"
                      className="flex h-10 w-10 items-center justify-center rounded-full bg-primary text-primary-foreground font-semibold hover:opacity-90 transition-opacity cursor-pointer"
                    >
                      {getInitial()}
                    </button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end" className="w-48">
                    <DropdownMenuItem
                      onClick={() => router.push("/chat")}
                      className="cursor-pointer"
                    >
                      התחל לשוחח
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              ) : (
                <Link href="/auth/login">
                  <InteractiveHoverButton>התחבר</InteractiveHoverButton>
                </Link>
              )}

              <MobileNavToggle
                isOpen={isOpen}
                onClick={() => setIsOpen(!isOpen)}
              />
            </div>
          </MobileNavHeader>
          <MobileNavMenu isOpen={isOpen} onClose={() => setIsOpen(false)}>
            <div className="flex flex-col gap-4">
              {navItems.map((item, idx) => (
                <Link
                  key={idx}
                  href={item.link}
                  onClick={() => setIsOpen(false)}
                  className="text-lg font-medium text-neutral-600 dark:text-neutral-300"
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
