import Link from "next/link";
import { ContactForm } from "@/components/marketing/contact-form";

type BetaAccessPanelProps = {
  source: "auth-login" | "auth-signup";
};

export function BetaAccessPanel({ source }: BetaAccessPanelProps) {
  return (
    <div className="w-full max-w-md mx-auto">
      <div className="mb-10 text-center sm:text-left">
        <div className="inline-flex items-center justify-center px-3 py-1 mb-6 rounded-full border border-gray-200 bg-gray-50/50">
          <span className="w-1.5 h-1.5 rounded-full bg-black mr-2 animate-pulse"></span>
          <span className="text-[11px] font-medium text-gray-600 uppercase tracking-widest">Private Beta</span>
        </div>
        <h1 className="text-3xl font-medium tracking-tight text-gray-900 mb-3">
          Request Access
        </h1>
        <p className="text-[15px] text-gray-500 leading-relaxed">
          AGENTS24 is currently in private beta. Send us a note with what you're building, and we'll get back to you shortly.
        </p>
      </div>

      <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-6 sm:p-8">
        <ContactForm
          source={source}
          compact
          submitLabel="Request access"
          successMessage="Request received. We will be in touch soon."
        />
      </div>

      <div className="mt-8 flex items-center justify-center sm:justify-start gap-4 text-sm font-medium">
        <Link 
          href="/contact" 
          className="text-gray-400 hover:text-black transition-colors flex items-center gap-2"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"></path></svg>
          Contact Support
        </Link>
      </div>
    </div>
  );
}
