import Link from "next/link";
import { ContactForm } from "@/components/marketing/contact-form";

export default function ContactPage() {
  return (
    <div className="min-h-screen bg-white selection:bg-black selection:text-white flex flex-col md:flex-row">
      {/* Left column: Text */}
      <div className="flex-1 flex items-center justify-center p-8 sm:p-12 lg:p-24 relative">
        {/* Separation Line (Desktop only, doesn't reach top/bottom) */}
        <div className="absolute right-0 top-32 bottom-32 w-px bg-gray-100 hidden md:block" />
        {/* Separation Line (Mobile only, added bottom border) */}
        <div className="absolute bottom-0 left-8 right-8 h-px bg-gray-100 md:hidden" />
        
        <div className="w-full max-w-md">
          <h1 className="text-4xl sm:text-5xl font-medium tracking-tight text-gray-900 mb-6">
            Get in touch
          </h1>
          <p className="text-lg text-gray-500 leading-relaxed mb-16">
            For early access, product feedback, partnership notes, or coordination. Messages go directly to the builders.
          </p>

          <div className="space-y-12">
            <div>
              <p className="text-xs font-mono text-gray-400 uppercase tracking-widest mb-3">Direct Email</p>
              <a 
                href="mailto:danielbenassaya2626@gmail.com" 
                className="text-lg font-medium text-gray-900 hover:text-gray-500 transition-colors"
              >
                danielbenassaya2626@gmail.com
              </a>
            </div>
          </div>
        </div>
      </div>

      {/* Right column: Form */}
      <div className="flex-1 flex items-center justify-center p-8 sm:p-12 lg:p-24 bg-gray-50/10 w-full">
        <div className="w-full max-w-2xl">
          <ContactForm source="contact-page" submitLabel="Send message" />
        </div>
      </div>
    </div>
  );
}
