import Link from "next/link";
import { MarketingPage } from "@/components/layout/MarketingPage";
import { IconMail, IconBrandLinkedin, IconBrandTwitter } from "@tabler/icons-react";

export default function ContactPage() {
  return (
    <MarketingPage
      title="צור קשר"
      description="אנחנו כאן לכל שאלה, הצעה או שיתוף פעולה."
    >
      <div className="w-full max-w-2xl mx-auto mt-10 grid grid-cols-1 md:grid-cols-2 gap-8">
        <div className="bg-white/10 backdrop-blur-md rounded-2xl p-8 flex flex-col items-center text-center space-y-4 hover:bg-white/20 transition-colors">
          <IconMail className="w-12 h-12 text-white" />
          <h3 className="text-xl font-bold text-white">כתבו לנו</h3>
          <p className="text-white/80">יש לכם שאלה? שלחו לנו מייל ונחזור אליכם בהקדם.</p>
          <Link href="mailto:team@kesher.ai" className="text-lg font-medium text-white underline decoration-white/50 hover:decoration-white">
            todaha26@gmail.com
          </Link>
        </div>

        <div className="bg-white/10 backdrop-blur-md rounded-2xl p-8 flex flex-col items-center text-center space-y-4 hover:bg-white/20 transition-colors">
          <h3 className="text-xl font-bold text-white">עקבו אחרינו</h3>
          <p className="text-white/80">הישארו מעודכנים ברשתות החברתיות.</p>
          <div className="flex gap-4">
            <Link href="https://www.linkedin.com/in/daniel-benassayag-978290227/" target="_blank" className="p-2 bg-white/10 rounded-full hover:bg-white/20 transition-colors">
              <IconBrandLinkedin className="w-6 h-6 text-white" />
            </Link>
            <Link href="https://x.com/DBenassaya" target="_blank" className="p-2 bg-white/10 rounded-full hover:bg-white/20 transition-colors">
              <IconBrandTwitter className="w-6 h-6 text-white" />
            </Link>
          </div>
        </div>
      </div>
    </MarketingPage>
  );
}

