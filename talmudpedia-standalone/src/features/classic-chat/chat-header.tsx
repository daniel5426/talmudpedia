import { Moon, Search, Sun } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useTheme } from "@/components/theme-provider";
import { cn } from "@/lib/utils";

type ChatHeaderProps = {
  isScrolled: boolean;
};

export function ChatHeader({ isScrolled }: ChatHeaderProps) {
  const { theme, setTheme } = useTheme();

  const toggleTheme = () => {
    setTheme(theme === "dark" ? "light" : "dark");
  };

  return (
    <header
      className={cn(
        "relative z-30 shrink-0 overflow-visible bg-background/100 supports-[backdrop-filter]:bg-background/100 transition-[background-color,backdrop-filter] duration-300",
        isScrolled &&
          "bg-background/80 backdrop-blur-md supports-[backdrop-filter]:bg-background/65"
      )}
    >
      <div className="flex h-12 items-center justify-end gap-1 px-3">
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8 rounded-md"
        >
          <Search className="size-3.5" />
          <span className="sr-only">Search</span>
        </Button>

        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8 rounded-md"
          onClick={toggleTheme}
          aria-label="Toggle theme"
        >
          <Sun className="size-3.5 rotate-0 scale-100 transition-transform dark:-rotate-90 dark:scale-0" />
          <Moon className="absolute size-3.5 rotate-90 scale-0 transition-transform dark:rotate-0 dark:scale-100" />
          <span className="sr-only">Toggle theme</span>
        </Button>
      </div>

      {/* Gradient fade below the header — matches AdminPageHeader exactly */}
      <div
        aria-hidden="true"
        className={cn(
          "pointer-events-none absolute inset-x-0 top-full z-10 h-5 bg-gradient-to-b from-background via-background/95 to-transparent transition-opacity duration-300 supports-[backdrop-filter]:from-background supports-[backdrop-filter]:via-background/70",
          isScrolled ? "opacity-100" : "opacity-0"
        )}
      />
    </header>
  );
}
