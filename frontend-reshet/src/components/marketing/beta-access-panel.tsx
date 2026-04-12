import Link from "next/link";
import { ContactForm } from "@/components/marketing/contact-form";

type BetaAccessPanelProps = {
  source: "auth-login" | "auth-signup";
};

export function BetaAccessPanel({ source }: BetaAccessPanelProps) {
  return (
    <div className="w-full max-w-xl mx-auto">
      <div className="mb-6 text-center sm:text-left">
        <h1 className="text-2xl font-medium tracking-tight text-gray-900 mb-2">
          Request Access
        </h1>
        <p className="text-sm text-gray-400 leading-relaxed">
          AGENTS24 is in private beta. Send us a quick note to get started.
        </p>
      </div>

      <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-5 sm:p-6">
        <ContactForm
          source={source}
          compact
          submitLabel="Request access"
          successMessage="Request received. We will be in touch soon."
        />
      </div>

      <div className="mt-6 flex items-center justify-center sm:justify-start gap-4 text-xs font-medium">
        <Link 
          href="/contact" 
          className="text-gray-400 hover:text-black transition-colors flex items-center gap-1.5"
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"></path></svg>
          Contact Support
        </Link>
      </div>
    </div>
  );
}
