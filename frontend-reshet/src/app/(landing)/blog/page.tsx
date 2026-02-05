import { MarketingPage } from "@/components/layout/MarketingPage";
import { BentoGrid, BentoGridItem } from "@/components/ui/bento-grid";
import { IconArticle, IconBulb, IconCode } from "@tabler/icons-react";

const blogPosts = [
  {
    title: "המהפכה של לימוד תורה עם AI",
    description: "כיצד בינה מלאכותית משנה את הדרך שבה אנו לומדים גמרא.",
    header: <div className="flex flex-1 w-full h-full min-h-[6rem] rounded-xl bg-gradient-to-br from-neutral-200 dark:from-neutral-900 dark:to-neutral-800 to-neutral-100" />,
    icon: <IconArticle className="h-4 w-4 text-neutral-500" />,
  },
  {
    title: "מאחורי הקלעים של מנוע החיפוש",
    description: "איך בנינו את האינדקס הסמנטי של כל ארון הספרים היהודי.",
    header: <div className="flex flex-1 w-full h-full min-h-[6rem] rounded-xl bg-gradient-to-br from-neutral-200 dark:from-neutral-900 dark:to-neutral-800 to-neutral-100" />,
    icon: <IconCode className="h-4 w-4 text-neutral-500" />,
  },
  {
    title: "5 טיפים לשימוש יעיל ברשת",
    description: "מדריך למשתמש המתחיל והמתקדם.",
    header: <div className="flex flex-1 w-full h-full min-h-[6rem] rounded-xl bg-gradient-to-br from-neutral-200 dark:from-neutral-900 dark:to-neutral-800 to-neutral-100" />,
    icon: <IconBulb className="h-4 w-4 text-neutral-500" />,
  },
];

export default function BlogPage() {
  return (
    <MarketingPage
      title="בלוג"
      description="תובנות, עדכונים ומדריכים על לימוד תורה בעידן הדיגיטלי."
    >
      <div className="w-full mt-10">
        <BentoGrid className="max-w-4xl mx-auto">
          {blogPosts.map((item, i) => (
            <BentoGridItem
              key={i}
              title={item.title}
              description={item.description}
              header={item.header}
              icon={item.icon}
              className={i === 0 ? "md:col-span-2" : ""}
            />
          ))}
        </BentoGrid>
      </div>
    </MarketingPage>
  );
}

