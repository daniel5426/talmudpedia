import type { ReactNode } from "react";

type MarketingPageProps = {
  title: string;
  subTitle?: string;
  description?: string;
  children?: ReactNode;
};

export function MarketingPage({
  title,
  subTitle,
  description,
  children,
}: MarketingPageProps) {
  return (
    <section className="flex min-h-screen flex-col items-center pt-32 pb-20 px-6 text-white">
      <div className="mx-auto flex w-full max-w-7xl flex-col items-center gap-12 text-center">
        <div className="space-y-6 max-w-3xl">
          <p className="text-sm uppercase tracking-[0.3em] text-white/70">
            {subTitle}
          </p>
          <h1 className="text-4xl md:text-6xl font-bold tracking-tight">{title}</h1>
          {description && (
            <p className="text-xl leading-relaxed text-white/90">
              {description}
            </p>
          )}
        </div>
        {children}
      </div>
    </section>
  );
}

