import { MarketingPage } from "@/components/layout/MarketingPage";

export default function ContactPage() {
  return (
    <MarketingPage
      title="Contact page removed"
      subTitle="Cleanup"
      description="The old contact and social content was tied to the previous product story. This route remains a placeholder until the new platform-facing contact flow is defined."
    >
      <div className="w-full max-w-2xl rounded-[2rem] border border-slate-200/80 bg-white/80 p-8 text-left shadow-sm backdrop-blur">
        <p className="text-base leading-7 text-slate-600">
          No public contact flow is being introduced in this phase.
        </p>
        <p className="mt-4 text-sm leading-6 text-slate-500">
          This page exists only to avoid carrying forward outdated product messaging.
        </p>
      </div>
    </MarketingPage>
  );
}
