import { Languages, Moon, Sun } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { SidebarTrigger } from "@/components/ui/sidebar";
import { useTheme } from "@/components/theme-provider";
import { cn } from "@/lib/utils";
import { useLocale } from "./locale-context";

type ChatHeaderProps = {
  isScrolled: boolean;
  isLoadingClients: boolean;
  onSelectedClientChange: (clientId: string) => void;
  selectedClientId: string | null;
  clients: Array<{
    id: string;
    name: string;
    sector: string;
  }>;
};

export function ChatHeader({
  isScrolled,
  isLoadingClients,
  onSelectedClientChange,
  selectedClientId,
  clients,
}: ChatHeaderProps) {
  const { theme, setTheme } = useTheme();
  const { locale, toggleLocale } = useLocale();
  const isHebrew = locale === "he";

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
      <div className="relative flex h-12 items-center justify-end gap-1 px-3">
        <div className="absolute start-3 top-1/2 -translate-y-1/2 md:hidden">
          <SidebarTrigger
            aria-label={isHebrew ? "פתח סרגל צד" : "Open sidebar"}
            className="h-8 w-8 rounded-md"
          />
        </div>

        <div className="flex min-w-0 items-center justify-end gap-1">
          <Select
            disabled={isLoadingClients || clients.length === 0}
            onValueChange={onSelectedClientChange}
            value={selectedClientId || undefined}
          >
            <SelectTrigger className="h-8 w-[min(220px,calc(100vw-9rem))] justify-between sm:w-[220px]">
              <SelectValue placeholder={isHebrew ? "בחר לקוח דמו" : "Select demo client"} />
            </SelectTrigger>
            <SelectContent align="end">
              {clients.map((client) => (
                <SelectItem key={client.id} value={client.id}>
                  {client.name} ({client.id})
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 rounded-md"
            onClick={toggleLocale}
            aria-label={isHebrew ? "Switch to English" : "העבר לעברית"}
          >
            <Languages className="size-3.5" />
            <span className="sr-only">{isHebrew ? "Switch to English" : "Switch to Hebrew"}</span>
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
