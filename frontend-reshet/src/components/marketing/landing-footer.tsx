"use client";

import Link from "next/link";

import { PLATFORM_DOMAINS } from "@/components/landing/v9/platformDomains";
import { authService } from "@/services";

type LandingFooterProps = {
  onSelectDomain: (index: number) => void;
};

export function LandingFooter({ onSelectDomain }: LandingFooterProps) {
  const signupUrl = authService.getSignupUrl("/admin/agents/playground");
  const loginUrl = authService.getLoginUrl("/admin/dashboard");

  return (
    <div className="max-w-[1100px] mx-auto mb-24 -mt-20 relative">
      <div className="grid gap-10 md:grid-cols-4">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-gray-500">
            Platform
          </p>
          <ul className="mt-4 space-y-2.5">
            {PLATFORM_DOMAINS.map((domain, index) => (
              <li key={domain.title}>
                <button
                  type="button"
                  onClick={() => onSelectDomain(index)}
                  className="text-left text-sm text-gray-400 transition-colors hover:text-white"
                >
                  {domain.title}
                </button>
              </li>
            ))}
          </ul>
        </div>

        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-gray-500">
            Access
          </p>
          <ul className="mt-4 space-y-2.5">
            <li>
              <a href={signupUrl} className="text-sm text-gray-400 transition-colors hover:text-white">
                Request access
              </a>
            </li>
            <li>
              <a href={loginUrl} className="text-sm text-gray-400 transition-colors hover:text-white">
                Operator login
              </a>
            </li>
            <li>
              <Link href="/contact" className="text-sm text-gray-400 transition-colors hover:text-white">
                Contact
              </Link>
            </li>
          </ul>
        </div>

        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-gray-500">
            Resources
          </p>
          <ul className="mt-4 space-y-2.5">
            <li>
              <Link
                href="https://docs.agents24.dev/"
                target="_blank"
                rel="noreferrer"
                className="text-sm text-gray-400 transition-colors hover:text-white"
              >
                Docs
              </Link>
            </li>
            <li>
              <Link href="/privacy" className="text-sm text-gray-400 transition-colors hover:text-white">
                Privacy Policy
              </Link>
            </li>
            <li>
              <Link href="/terms" className="text-sm text-gray-400 transition-colors hover:text-white">
                Terms of Service
              </Link>
            </li>
          </ul>
        </div>

        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-gray-500">
            Contact
          </p>
          <div className="mt-4 max-w-xs text-sm leading-6 text-gray-400">
            Private beta access, partnership notes, and production testing requests go straight to
            Daniel.
            <div className="mt-3 text-white">danielbenassaya2626@gmail.com</div>
          </div>
        </div>
      </div>
    </div>
  );
}
