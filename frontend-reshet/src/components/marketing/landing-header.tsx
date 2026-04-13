"use client";

import Link from "next/link";
import Image from "next/image";
import { AnimatePresence, motion } from "motion/react";
import { ChevronDown } from "lucide-react";
import { useEffect, useState } from "react";

import { PLATFORM_DOMAINS } from "@/components/landing/v9/platformDomains";

import { usePathname, useRouter } from "next/navigation";

type LandingHeaderProps = {
  scrolled?: boolean;
  onSelectDomain?: (index: number) => void;
};

export function LandingHeader({ scrolled: propsScrolled, onSelectDomain }: LandingHeaderProps) {
  const [internalScrolled, setInternalScrolled] = useState(false);
  const [platformOpen, setPlatformOpen] = useState(false);
  const pathname = usePathname();
  const router = useRouter();

  const isHome = pathname === "/";
  
  useEffect(() => {
    // Only use internal scroll logic if we are not on the home page (where LandingV9 handles it)
    // or if the prop isn't explicitly passed.
    if (isHome && propsScrolled !== undefined) {
      return;
    }

    const onScroll = () => setInternalScrolled(window.scrollY > 40);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [isHome, propsScrolled]);

  // Use the prop if we're on home and it's defined, otherwise use internal scroll state
  const scrolled = (isHome && propsScrolled !== undefined) ? propsScrolled : internalScrolled;

  const handleSelectDomain = (index: number) => {
    if (onSelectDomain) {
      onSelectDomain(index);
    } else {
      router.push("/#platform");
    }
    setPlatformOpen(false);
  };

  return (
    <nav
      className={`fixed top-0 z-50 w-full transition-all duration-500 ease-out ${
        scrolled ? "px-4 pt-3 md:px-8" : ""
      }`}
    >
      <div
        className={`mx-auto flex min-h-14 items-center transition-all duration-500 ease-out ${
          scrolled
            ? "max-w-5xl rounded-[2rem] border border-gray-200/70 bg-white/92 px-5 backdrop-blur-xl"
            : "max-w-[1200px] bg-transparent px-6"
        }`}
      >
        <Link href="/" className="flex items-center gap-2.5">
          <Image
            src="/kesher.png"
            alt="AGENTS24"
            width={28}
            height={28}
            className="h-7 w-7 rounded-lg"
          />
          <span className="text-lg font-bold">AGENTS24</span>
        </Link>

        <div className="flex-1" />

        <div className="hidden items-center gap-6 text-[13px] font-medium text-[#4b5563] md:flex">
          <div
            className="relative"
            onMouseEnter={() => setPlatformOpen(true)}
            onMouseLeave={() => setPlatformOpen(false)}
          >
            <button
              type="button"
              className="flex items-center gap-1 transition-colors hover:text-black"
            >
              Platform <ChevronDown className="h-3.5 w-3.5 opacity-60" />
            </button>

            <AnimatePresence>
              {platformOpen ? (
                <motion.div
                  initial={{ opacity: 0, y: 8, scale: 0.99 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0, y: 4, scale: 0.99 }}
                  transition={{ duration: 0.15, ease: "easeOut" }}
                  className="absolute left-0 top-full mt-2 w-[200px] rounded-2xl border border-gray-100 bg-white p-1.5 shadow-[0_10px_40px_-15px_rgba(0,0,0,0.1)]"
                >
                  {/* Invisible bridge to prevent hover flickering */}
                  <div className="absolute -top-3 left-0 right-0 h-4 bg-transparent" />
                  
                  <div className="flex flex-col">
                    {PLATFORM_DOMAINS.map((domain, index) => (
                      <button
                        key={domain.title}
                        type="button"
                        onClick={() => handleSelectDomain(index)}
                        className="group flex items-center justify-between rounded-xl px-3 py-2 text-left transition-colors hover:bg-gray-50"
                      >
                        <span className="text-[13px] font-medium text-gray-600 transition-colors group-hover:text-black">
                          {domain.title}
                        </span>
                        <svg 
                          width="12" 
                          height="12" 
                          viewBox="0 0 24 24" 
                          fill="none" 
                          stroke="currentColor" 
                          strokeWidth="2.5" 
                          strokeLinecap="round" 
                          strokeLinejoin="round" 
                          className="text-gray-300 opacity-0 transition-all group-hover:opacity-100 group-hover:translate-x-0.5"
                        >
                          <path d="M5 12h14m-7-7 7 7-7 7" />
                        </svg>
                      </button>
                    ))}
                  </div>
                </motion.div>
              ) : null}
            </AnimatePresence>
          </div>

          <Link
            href="https://docs.agents24.dev/"
            target="_blank"
            rel="noreferrer"
            className="transition-colors hover:text-black"
          >
            Docs
          </Link>
          <Link href="/contact" className="transition-colors hover:text-black">
            Contact
          </Link>
        </div>

        <div className="flex-1" />

        <div className="hidden items-center gap-3 md:flex">
          <Link
            href="/auth/login"
            className="px-3 py-1.5 text-[13px] font-medium text-[#4b5563] transition-colors hover:text-black"
          >
            Log in
          </Link>
          <Link
            href="/auth/signup"
            className="rounded-full bg-black px-4 py-2 text-[13px] font-medium text-white transition-colors hover:bg-gray-900"
          >
            Start building
          </Link>
        </div>
      </div>
    </nav>
  );
}
