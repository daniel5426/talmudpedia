"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { BotImputArea } from "@/components/BotImputArea";
import DataPoints from "@/components/animations/data-points";
import { savePendingChatMessage } from "@/lib/chatPrefill";
import { useLayoutStore } from "@/lib/store/useLayoutStore";
import { BentoGrid, BentoGridItem } from "@/components/ui/bento-grid";
import { EvervaultCard, Icon } from "@/components/ui/evervault-card";
import { IconSearch, IconSparkles, IconBook, IconWorld } from "@tabler/icons-react";

type LibraryCardProps = {
  title: string;
  description: string;
  evervaultText: string;
};

function LibraryCard({ title, description, evervaultText }: LibraryCardProps) {
  return (
    <div className="border border-black/[0.2] dark:border-white/[0.2] flex flex-col items-start max-w-[8rem] md:max-w-[11rem] bg-white/10 backdrop-blur-md mx-auto p-1 md:p-4 relative h-[12rem] md:h-[18rem]">
      <Icon className="absolute h-4 w-4 md:h-5  md:w-5 -top-2 -left-2 md:-top-3 md:-left-3 dark:text-white text-black" />
      <Icon className="absolute h-4 w-4 md:h-5  md:w-5 -bottom-2 -left-2 md:-bottom-3 md:-left-3 dark:text-white text-black" />
      <Icon className="absolute h-4 w-4 md:h-5  md:w-5 -top-2 -right-2 md:-top-3 md:-right-3 dark:text-white text-black" />
      <Icon className="absolute h-4 w-4 md:h-5  md:w-5 -bottom-2 -right-2 md:-bottom-3 md:-right-3 dark:text-white text-black" />
      <EvervaultCard text={evervaultText} className="size-[6.5rem] md:size-[9rem]" />
      <h2 className="dark:text-white text-white mt-2 md:mt-3 text-xs md:text-sm font-light">
        {description}
      </h2>
      <p className="text-xs md:text-sm border font-light dark:border-white/[0.2] border-black/[0.2] rounded-full mt-1 md:mt-2 text-black dark:text-white px-1.5 md:px-2 py-0.5">
        עיין עכשיו
      </p>
    </div>
  );
}

type LandingPageProps = {
  title?: string;
  description?: string;
};

export function LandingPage({
  title = "ברוך הבא לרשת",
  description = "המקום שבו אפשר לחפש ולעיין בכל התורה כולה במשפט אחד",
}: LandingPageProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [isRedirecting, setIsRedirecting] = useState(false);
  const router = useRouter();
  const setActiveChatId = useLayoutStore((state) => state.setActiveChatId);
  const [scrollY, setScrollY] = useState(0);
  const [inputValue, setInputValue] = useState("");
  const [libraryScrollDuration, setLibraryScrollDuration] = useState(10);
  useEffect(() => {
    setActiveChatId(null);
  }, [setActiveChatId]);

  useEffect(() => {
    const handleScroll = () => {
      setScrollY(window.scrollY);
    };

    window.addEventListener("scroll", handleScroll);
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  const handleLandingSubmit = (message: { text: string; files: any[] }) => {
    if (isRedirecting) return;
    setActiveChatId(null);
    savePendingChatMessage(message);
    setIsRedirecting(true);
    router.push("/chat");
  };

  const features = [
    {
      title: "חיפוש עמוק",
      description: "מצא מקורות מדויקים מתוך אלפי ספרים בשניות.",
      header: <div className="flex flex-1 w-full h-full min-h-[6rem] rounded-xl bg-gradient-to-br from-neutral-200 dark:from-neutral-900 dark:to-neutral-800 to-neutral-100" />,
      icon: <IconSearch className="h-4 w-4 text-neutral-500" />,
    },
    {
      title: "הסברים מבוססי AI",
      description: "קבל הסברים ברורים ומעמיקים לכל סוגיה תורנית.",
      header: <div className="flex flex-1 w-full h-full min-h-[6rem] rounded-xl bg-gradient-to-br from-neutral-200 dark:from-neutral-900 dark:to-neutral-800 to-neutral-100" />,
      icon: <IconSparkles className="h-4 w-4 text-neutral-500" />,
    },
    {
      title: "אינטגרציה של מקורות",
      description: "ראה את המקורות המקוריים לצד ההסברים.",
      header: <div className="flex flex-1 w-full h-full min-h-[6rem] rounded-xl bg-gradient-to-br from-neutral-200 dark:from-neutral-900 dark:to-neutral-800 to-neutral-100" />,
      icon: <IconBook className="h-4 w-4 text-neutral-500" />,
    },
    {
      title: "תמיכה רב-לשונית",
      description: "חפש וקרא בעברית ובאנגלית בצורה חלקה.",
      header: <div className="flex flex-1 w-full h-full min-h-[6rem] rounded-xl bg-gradient-to-br from-neutral-200 dark:from-neutral-900 dark:to-neutral-800 to-neutral-100" />,
      icon: <IconWorld className="h-4 w-4 text-neutral-500" />,
    },
  ];

  const libraryItems = [
    {
      title: "תלמוד בבלי",
      description: "התלמוד הבבלי הוא יסוד מרכזי ללימוד ההלכה והסוגיות התורניות",
      evervaultText: "תלמוד בבלי",
    },
    {
      title: "משנה תורה",
      description: "חיבורו השיטתי של הרמב\"ם המסכם את כל ההלכה היהודית",
      evervaultText: "משנה תורה",
    },
    {
      title: "שולחן ערוך",
      description: "קודקס ההלכה המרכזי המסכם את הפסיקה הספרדית והאשכנזית",
      evervaultText: "שולחן ערוך",
    },
    {
      title: "תנ\"ך",
      description: "המקור הראשון לתורה שבכתב עם כל ספרי המקרא",
      evervaultText: "תנ\"ך",
    },
    {
      title: 'רש"י',
      description: "פירושו הקלאסי של רש\"י על התלמוד והתנ״ך",
      evervaultText: 'רש"י',
    },
    {
      title: "משנה",
      description: "היסוד לתורה שבעל פה והמקור העיקרי לדיוני התלמוד",
      evervaultText: "משנה",
    },
    {
      title: "זוהר",
      description: "הספר המרכזי בתורת הקבלה והסוד",
      evervaultText: "זוהר",
    },
    {
      title: "ספר החינוך",
      description: "ביאור מצוות התורה על סדר פרשיות השבוע",
      evervaultText: "ספר החינוך",
    },
    {
      title: "משנה ברורה",
      description: "פירוש הלכתי יסודי על אורח חיים לשולחן ערוך",
      evervaultText: "משנה ברורה",
    },
    {
      title: "חפץ חיים",
      description: "ספר היסוד בדיני לשון הרע והנהגת הדיבור",
      evervaultText: "חפץ חיים",
    },
  ];

  return (
    <div ref={containerRef} className="relative flex flex-col bg-transparent min-h-screen">
      {/* Hero Section */}
      <div className="flex flex-col items-center px-4 pt-20 pb-22 relative z-10">
        <div className="relative flex flex-col items-center justify-center w-full max-w-4xl mx-auto p-4 min-h-[60vh]">
          <div className="py-8 text-center space-y-6">
            <div className="text-5xl md:text-5xl font-bold tracking-tighter">
              {title}
            </div>
            {description && (
              <p className="text-xl md:text-2xl text-white/90 max-w-2xl mx-auto leading-relaxed">
                {description}
              </p>
            )}
          </div>
          <div className="w-full max-w-3xl mt-2">
             <BotImputArea
                className="bg-white/10 backdrop-blur-md border-none shadow-2xl"
                textareaRef={useRef(null)}
                handleSubmit={handleLandingSubmit}
                isLoading={isRedirecting}
              />
          </div>
        </div>
      </div>

      {/* Background Animation Section */}
      <div className="w-full h-[550px] md:h-[900px] flex justify-center items-center relative z-0">
         <DataPoints scrollOffset={scrollY} />
      </div>

      {/* Features Section */}
      <section className="relative z-10 py-20 px-4">
        <div className="max-w-7xl mx-auto">
          <h2 className="text-3xl md:text-5xl font-bold text-center text-white mb-12">
            תכונות מרכזיות
          </h2>
          <BentoGrid className="max-w-4xl mx-auto">
            {features.map((item, i) => (
              <BentoGridItem
                key={i}
                title={item.title}
                description={item.description}
                header={item.header}
                icon={item.icon}
                className={i === 3 || i === 6 ? "md:col-span-2" : ""}
              />
            ))}
          </BentoGrid>
        </div>
      </section>

      {/* Library Section */}
      <section className="relative z-10 py-20 px-1">
        <div className="max-w-[100rem] mx-auto text-center">
          <h2 className="text-3xl md:text-5xl font-bold text-white mb-12">
            הספרייה שלנו
          </h2>
          <div
            className="relative px-10 library-scroll-wrapper"
            style={{ ["--library-scroll-duration" as string]: `${libraryScrollDuration}s` }}
          >
            <div className="overflow-hidden">
              <div className="flex library-scroll">
                {[...libraryItems, ...libraryItems].map((item, index) => (
                  <div
                    key={`${item.title}-${index}`}
                    className="shrink-0 basis-32 md:basis-50"
                  >
                    <LibraryCard
                      title={item.title}
                      description={item.description}
                      evervaultText={item.evervaultText}
                    />
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>


    </div>
  );
}
