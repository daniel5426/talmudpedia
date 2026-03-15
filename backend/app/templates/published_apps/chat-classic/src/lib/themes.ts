export type Palette = {
  id: number;
  name: string;
  description: string;
  light: Record<string, string>;
  dark: Record<string, string>;
};

export const palettes: Palette[] = [
  {
    id: 1,
    name: "Warm Terracotta",
    description: "Earthy, warm, inviting",
    light: {
      "--background": "oklch(0.98 0.01 45)",
      "--foreground": "oklch(0.25 0.05 45)",
      "--primary": "oklch(0.45 0.12 35)",
      "--primary-foreground": "oklch(0.98 0.01 45)",
      "--muted": "oklch(0.95 0.02 50)",
      "--muted-foreground": "oklch(0.5 0.04 40)",
      "--destructive": "oklch(0.55 0.2 25)",
      "--border": "oklch(0.9 0.02 45)",
      "--ring": "oklch(0.45 0.12 35)",
    },
    dark: {
      "--background": "oklch(0.2 0.03 45)",
      "--foreground": "oklch(0.95 0.01 50)",
      "--primary": "oklch(0.65 0.15 35)",
      "--primary-foreground": "oklch(0.2 0.03 45)",
      "--muted": "oklch(0.3 0.04 45)",
      "--muted-foreground": "oklch(0.7 0.03 50)",
      "--destructive": "oklch(0.65 0.22 25)",
      "--border": "oklch(0.35 0.03 45)",
      "--ring": "oklch(0.65 0.15 35)",
    },
  },
  {
    id: 5,
    name: "Ocean Breeze",
    description: "Calm, refreshing, professional",
    light: {
      "--background": "oklch(1 0 0)",
      "--foreground": "oklch(0.2 0.02 240)",
      "--sidebar": "oklch(0.9789 0.006 223.46)",
      "--primary": "oklch(0.5 0.15 220)",
      "--primary-foreground": "oklch(0.99 0.01 220)",
      "--muted": "oklch(0.95 0.02 225)",
      "--muted-foreground": "oklch(0.45 0.05 230)",
      "--destructive": "oklch(0.55 0.2 25)",
      "--border": "oklch(0.9 0.02 220)",
      "--ring": "oklch(0.5 0.15 220)",
      "--gradient-from": "#dff2f4",
      "--gradient-to": "#1ca4ac",
      "--chat-background": "oklch(1 0 0)",
    },
    dark: {
      "--background": "oklch(0.18 0.02 240)",
      "--foreground": "oklch(0.95 0.01 220)",
      "--primary": "oklch(0.65 0.18 220)",
      "--primary-foreground": "oklch(0.18 0.02 240)",
      "--muted": "oklch(0.28 0.03 235)",
      "--muted-foreground": "oklch(0.7 0.04 225)",
      "--destructive": "oklch(0.65 0.22 25)",
      "--border": "oklch(0.33 0.02 230)",
      "--ring": "oklch(0.65 0.18 220)",
    },
  },
  {
    id: 8,
    name: "Minimal Gray",
    description: "Clean, professional, versatile",
    light: {
      "--background": "oklch(1 0 0)",
      "--foreground": "oklch(0.15 0 0)",
      "--primary": "oklch(0.25 0 0)",
      "--primary-foreground": "oklch(0.98 0 0)",
      "--muted": "oklch(0.96 0 0)",
      "--muted-foreground": "oklch(0.5 0 0)",
      "--destructive": "oklch(0.55 0.2 25)",
      "--border": "oklch(0.9 0 0)",
      "--ring": "oklch(0.25 0 0)",
    },
    dark: {
      "--background": "oklch(0.12 0 0)",
      "--foreground": "oklch(0.98 0 0)",
      "--primary": "oklch(0.9 0 0)",
      "--primary-foreground": "oklch(0.12 0 0)",
      "--muted": "oklch(0.22 0 0)",
      "--muted-foreground": "oklch(0.7 0 0)",
      "--destructive": "oklch(0.65 0.22 25)",
      "--border": "oklch(0.28 0 0)",
      "--ring": "oklch(0.9 0 0)",
    },
  },
  {
    id: 11,
    name: "GPT Classic",
    description: "Clean monochrome aesthetic",
    light: {
      "--background": "oklch(1 0 0)",
      "--foreground": "oklch(0.1 0 0)",
      "--primary": "oklch(0.1 0 0)",
      "--primary-foreground": "oklch(1 0 0)",
      "--muted": "oklch(0.9821 0 0)",
      "--muted-foreground": "oklch(0.5 0 0)",
      "--destructive": "oklch(0.55 0.2 25)",
      "--border": "oklch(0.91 0 0)",
      "--sidebar": "oklch(0.9821 0 0)",
      "--ring": "oklch(0.1 0 0)",
      "--chat-background": "oklch(1 0 0)",
    },
    dark: {
      "--background": "oklch(0.15 0 0)",
      "--foreground": "oklch(0.98 0 0)",
      "--primary": "oklch(0.98 0 0)",
      "--primary-foreground": "oklch(0.15 0 0)",
      "--muted": "oklch(0.25 0 0)",
      "--muted-foreground": "oklch(0.7 0 0)",
      "--destructive": "oklch(0.65 0.22 25)",
      "--border": "oklch(0.32 0 0)",
      "--ring": "oklch(0.98 0 0)",
      "--chat-background": "oklch(0.15 0 0)",
    },
  },
  {
    id: 13,
    name: "Arctic Frost",
    description: "Crisp, high-contrast ice blue",
    light: {
      "--background": "oklch(1 0 0)",
      "--foreground": "oklch(0.12 0.03 230)",
      "--primary": "oklch(0.5 0.15 210)",
      "--primary-foreground": "oklch(1 0 0)",
      "--muted": "oklch(0.97 0.01 210)",
      "--muted-foreground": "oklch(0.4 0.05 210)",
      "--destructive": "oklch(0.55 0.2 25)",
      "--border": "oklch(0.92 0.02 210)",
      "--ring": "oklch(0.5 0.15 210)",
      "--gradient-from": "#f0f9ff",
      "--gradient-to": "#e0f2fe",
      "--chat-background": "oklch(1 0 0)",
    },
    dark: {
      "--background": "oklch(0.1 0.02 220)",
      "--foreground": "oklch(0.98 0.01 200)",
      "--primary": "oklch(0.7 0.12 200)",
      "--primary-foreground": "oklch(0.1 0.02 220)",
      "--muted": "oklch(0.18 0.03 220)",
      "--muted-foreground": "oklch(0.8 0.02 200)",
      "--destructive": "oklch(0.65 0.22 25)",
      "--border": "oklch(0.25 0.03 220)",
      "--ring": "oklch(0.7 0.12 200)",
      "--chat-background": "oklch(0.1 0.02 220)",
    },
  },
];

export function applyPalette(paletteId: number) {
  if (typeof window === "undefined") return;
  const palette = palettes.find((candidate) => candidate.id === paletteId);
  if (!palette) return;

  const root = document.documentElement;
  Array.from(root.style)
    .filter((name) => name.startsWith("--p-light-") || name.startsWith("--p-dark-"))
    .forEach((name) => root.style.removeProperty(name));

  Object.entries(palette.light).forEach(([property, value]) => {
    root.style.setProperty(`--p-light-${property.slice(2)}`, value);
  });
  Object.entries(palette.dark).forEach(([property, value]) => {
    root.style.setProperty(`--p-dark-${property.slice(2)}`, value);
  });

  window.localStorage.setItem("palette", String(paletteId));
}

export function initPalette() {
  if (typeof window === "undefined") return;
  const stored = Number(window.localStorage.getItem("palette") || 5);
  const paletteId = palettes.some((palette) => palette.id === stored) ? stored : 5;
  applyPalette(paletteId);
}
