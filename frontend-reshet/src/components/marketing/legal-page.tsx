import Link from "next/link";

type LegalSection = {
  title: string;
  paragraphs: string[];
};

type LegalPageProps = {
  eyebrow: string;
  title: string;
  description: string;
  effectiveDate: string;
  sections: LegalSection[];
};

export function LegalPage({
  eyebrow,
  title,
  description,
  effectiveDate,
  sections,
}: LegalPageProps) {
  return (
    <div className="min-h-screen bg-white selection:bg-black selection:text-white">
      <div className="mx-auto max-w-3xl px-6 py-32 sm:py-48">
        <header className="mb-16">
          <div className="flex items-center gap-4 mb-6">
            <span className="h-px bg-black flex-1 max-w-[2rem]"></span>
            <p className="text-xs font-mono uppercase tracking-widest text-gray-400">
              {eyebrow}
            </p>
          </div>
          
          <h1 className="text-4xl md:text-5xl font-medium tracking-tight text-gray-900 mb-6">
            {title}
          </h1>
          
          <p className="text-lg text-gray-500 leading-relaxed max-w-2xl">
            {description}
          </p>
          
          <div className="mt-8 flex items-center gap-3 text-sm text-gray-400 font-mono">
            <span>Effective:</span>
            <span className="text-gray-900">{effectiveDate}</span>
          </div>
        </header>

        <div className="space-y-16">
          {sections.map((section, idx) => (
            <section key={section.title} className="relative group">
              <div className="absolute -inset-y-6 -inset-x-6 sm:-inset-x-8 -z-10 rounded-2xl bg-gray-50/50 opacity-0 group-hover:opacity-100 transition-opacity duration-500"></div>
              
              <h2 className="text-xl font-medium text-gray-900 mb-5 tracking-tight flex items-center gap-4">
                <span className="text-[10px] font-mono text-gray-300 tracking-widest">
                  {(idx + 1).toString().padStart(2, '0')}
                </span>
                {section.title}
              </h2>
              
              <div className="space-y-5 text-gray-600 leading-relaxed text-[15px] sm:text-base">
                {section.paragraphs.map((paragraph, pIdx) => (
                  <p key={pIdx}>{paragraph}</p>
                ))}
              </div>
            </section>
          ))}
        </div>

        <footer className="mt-24 pt-8 border-t border-gray-100 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <p className="text-sm text-gray-400">
            © {new Date().getFullYear()} AGENTS24. All rights reserved.
          </p>
          <p className="text-sm text-gray-500 flex items-center gap-2">
            Questions? 
            <Link 
              href="/contact" 
              className="text-gray-900 font-medium hover:text-black hover:underline underline-offset-4 decoration-gray-300 transition-all"
            >
              Reach out to us
            </Link>
          </p>
        </footer>
      </div>
    </div>
  );
}
