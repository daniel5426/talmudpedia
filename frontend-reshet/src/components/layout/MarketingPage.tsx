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
    <section className="flex min-h-screen flex-col items-center px-6 pb-20 pt-32 text-slate-950">
      <div className="mx-auto flex w-full max-w-5xl flex-col items-center gap-10 text-center">
        <div className="space-y-6 max-w-3xl">
          <p className="text-sm uppercase tracking-[0.3em] text-slate-500">
            {subTitle}
          </p>
          <h1 className="text-4xl font-semibold tracking-[-0.04em] md:text-6xl">
            {title}
          </h1>
          {description && (
            <p className="text-xl leading-relaxed text-slate-600">
              {description}
            </p>
          )}
        </div>
        {children}
      </div>
    </section>
  );
}
