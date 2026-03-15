import { Check, Moon, Palette, Sun } from "lucide-react";

import { useTheme } from "@/components/theme-provider";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { palettes } from "@/lib/themes";

export function ThemeCustomizer() {
  const { theme, setTheme, paletteId, setPaletteId } = useTheme();

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" className="h-9 w-9">
          <Palette className="h-4 w-4" />
          <span className="sr-only">Customize theme</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-52">
        <DropdownMenuLabel>Color Palette</DropdownMenuLabel>
        <DropdownMenuSeparator />
        <div className="max-h-60 overflow-y-auto">
          {palettes.map((palette) => (
            <DropdownMenuItem
              key={palette.id}
              onClick={() => setPaletteId(palette.id)}
              className="flex items-center justify-between py-2"
            >
              <div className="flex flex-col gap-0.5">
                <div className="flex items-center gap-2">
                  <div
                    className="h-3 w-3 rounded-full border"
                    style={{ backgroundColor: palette.light["--primary"] }}
                  />
                  <span className="text-sm font-medium">{palette.name}</span>
                </div>
                <span className="line-clamp-1 text-[10px] text-muted-foreground">
                  {palette.description}
                </span>
              </div>
              {paletteId === palette.id ? <Check className="ml-2 h-4 w-4" /> : null}
            </DropdownMenuItem>
          ))}
        </div>
        <DropdownMenuSeparator />
        <DropdownMenuLabel>Mode</DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={() => setTheme("light")}>
          <Sun className="mr-2 h-4 w-4" />
          Light
          {theme === "light" ? <Check className="ml-auto h-4 w-4" /> : null}
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => setTheme("dark")}>
          <Moon className="mr-2 h-4 w-4" />
          Dark
          {theme === "dark" ? <Check className="ml-auto h-4 w-4" /> : null}
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => setTheme("system")}>
          <span className="mr-2">💻</span>
          System
          {theme === "system" ? <Check className="ml-auto h-4 w-4" /> : null}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
