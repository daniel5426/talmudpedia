import { MarketingPage } from "@/components/layout/MarketingPage";

export default function BlogPage() {
  return (
    <MarketingPage
      title="Blog page removed"
      subTitle="Cleanup"
      description="The old editorial and thought-leadership content no longer matches the platform. This route stays intentionally empty until a new content model exists."
    >
      <div className="w-full max-w-2xl rounded-[2rem] border border-slate-200/80 bg-white/80 p-8 text-left shadow-sm backdrop-blur">
        <p className="text-base leading-7 text-slate-600">
          No replacement blog or update feed is being shipped in this cleanup pass.
        </p>
      </div>
    </MarketingPage>
  );
}
