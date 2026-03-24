"use client";

import Link from "next/link";
import { ArrowRight } from "lucide-react";

/* ──────────────────────────────────────────────────────────
   Content Section (content-5 style)
   Centered logo with title and description
   ────────────────────────────────────────────────────────── */

export function ContentSection() {
  return (
    <section className="py-20 md:py-28 px-6">
      <div className="max-w-3xl mx-auto text-center">
        <div className="flex justify-center mb-10">
          <img
            src="/kesher.png"
            alt="AGENTS24"
            className="w-20 h-20 md:w-28 md:h-28 rounded-3xl shadow-lg"
          />
        </div>

        <h2 className="text-3xl md:text-[44px] font-semibold tracking-tight text-gray-900 leading-[1.1] mb-5">
          Seamless Integration
          <br />
          with your favorite Tools
        </h2>

        <p className="text-base text-gray-500 max-w-md mx-auto leading-relaxed mb-8">
          Connect seamlessly with popular platforms and services to enhance your
          workflow.
        </p>

        <Link
          href="/auth/signup"
          className="inline-flex items-center gap-2 px-6 py-3 rounded-xl border border-gray-200 bg-white text-sm font-medium text-gray-900 hover:bg-gray-50 transition-colors"
        >
          Get Started
        </Link>
      </div>
    </section>
  );
}

/* ──────────────────────────────────────────────────────────
   Logo Cloud (logo-cloud-2 style)
   Simple row of brand text logos with dividers
   ────────────────────────────────────────────────────────── */

const logos = [
  { name: "OpenAI", weight: "font-bold" },
  { name: "Anthropic", weight: "font-semibold" },
  { name: "Google", weight: "font-bold" },
  { name: "Mistral", weight: "font-semibold" },
  { name: "AWS", weight: "font-bold" },
  { name: "Vercel", weight: "font-semibold" },
];

export function LogoCloud() {
  return (
    <section className="py-12 md:py-16 px-6">
      <div className="max-w-4xl mx-auto">
        <p className="text-center text-xs font-medium text-gray-400 uppercase tracking-[0.15em] mb-8">
          Trusted by teams using
        </p>
        <div className="flex flex-wrap items-center justify-center gap-x-8 gap-y-4">
          {logos.map((logo, i) => (
            <div key={logo.name} className="flex items-center gap-8">
              <span
                className={`text-lg md:text-xl ${logo.weight} text-gray-400 tracking-tight`}
              >
                {logo.name}
              </span>
              {i < logos.length - 1 && (
                <div className="hidden md:block w-px h-5 bg-gray-200" />
              )}
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ──────────────────────────────────────────────────────────
   Testimonial (testimonials-1 style)
   Single centered card with company branding, quote, avatar
   ────────────────────────────────────────────────────────── */

export function TestimonialSection() {
  return (
    <section className="py-20 md:py-28 px-6">
      <div className="max-w-xl mx-auto">
        <div className="rounded-2xl border border-gray-200/80 bg-white p-8 md:p-10 shadow-sm">
          {/* Company indicator */}
          <div className="text-lg font-bold text-emerald-500 tracking-tight mb-6">
            AGENTS24
          </div>

          {/* Quote */}
          <blockquote className="text-base md:text-lg text-gray-700 leading-relaxed mb-8">
            &ldquo;AGENTS24 has transformed how we build and deploy AI agents.
            Their extensive platform and visual builder has significantly
            accelerated our workflow. The flexibility to customize every aspect
            allows us to create unique agent experiences.&rdquo;
          </blockquote>

          {/* Author */}
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-gradient-to-br from-gray-200 to-gray-300 flex items-center justify-center">
              <span className="text-sm font-bold text-gray-600">SC</span>
            </div>
            <div>
              <div className="text-sm font-semibold text-gray-900">
                Sarah Chen
              </div>
              <div className="text-sm text-gray-500">Head of AI, Fintech Corp</div>
            </div>
          </div>
        </div>

        {/* Logo cloud below testimonial */}
        <div className="flex items-center justify-center gap-6 mt-10">
          {["stripe", "anthropic", "vercel"].map((brand) => (
            <span
              key={brand}
              className="text-sm font-semibold text-gray-300 tracking-tight capitalize"
            >
              {brand}
            </span>
          ))}
        </div>
      </div>
    </section>
  );
}
