import {
  createContext,
  type ReactNode,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import { applyPalette, initPalette, palettes } from "@/lib/themes";

type ThemeMode = "light" | "dark" | "system";

type ThemeContextValue = {
  theme: ThemeMode;
  setTheme: (theme: ThemeMode) => void;
  paletteId: number;
  setPaletteId: (paletteId: number) => void;
};

const STORAGE_THEME_KEY = "talmudpedia-template-theme";
const STORAGE_PALETTE_KEY = "palette";
const DEFAULT_PALETTE_ID = 5;
const ThemeContext = createContext<ThemeContextValue | null>(null);

function resolveTheme(theme: ThemeMode): "light" | "dark" {
  if (theme !== "system") {
    return theme;
  }
  if (typeof window === "undefined") {
    return "light";
  }
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function applyResolvedTheme(theme: ThemeMode) {
  if (typeof document === "undefined") return;
  document.documentElement.classList.toggle("dark", resolveTheme(theme) === "dark");
}

export function bootstrapTheme() {
  if (typeof window === "undefined") return;
  initPalette();
  const storedTheme = window.localStorage.getItem(STORAGE_THEME_KEY) as ThemeMode | null;
  applyResolvedTheme(storedTheme || "system");
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<ThemeMode>(() => {
    if (typeof window === "undefined") return "system";
    return (window.localStorage.getItem(STORAGE_THEME_KEY) as ThemeMode | null) || "system";
  });
  const [paletteId, setPaletteIdState] = useState<number>(() => {
    if (typeof window === "undefined") return DEFAULT_PALETTE_ID;
    const stored = Number(window.localStorage.getItem(STORAGE_PALETTE_KEY) || DEFAULT_PALETTE_ID);
    return palettes.some((palette) => palette.id === stored) ? stored : DEFAULT_PALETTE_ID;
  });

  useEffect(() => {
    applyResolvedTheme(theme);
    if (typeof window === "undefined") return;
    window.localStorage.setItem(STORAGE_THEME_KEY, theme);

    if (theme !== "system") {
      return;
    }

    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const handleChange = () => applyResolvedTheme("system");
    media.addEventListener("change", handleChange);
    return () => media.removeEventListener("change", handleChange);
  }, [theme]);

  useEffect(() => {
    applyPalette(paletteId);
  }, [paletteId]);

  const value = useMemo(
    () => ({
      theme,
      setTheme: setThemeState,
      paletteId,
      setPaletteId: setPaletteIdState,
    }),
    [theme, paletteId],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const value = useContext(ThemeContext);
  if (!value) {
    throw new Error("useTheme must be used within ThemeProvider");
  }
  return value;
}
