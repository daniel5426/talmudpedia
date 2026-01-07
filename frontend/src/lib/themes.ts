export type Palette = {
  id: number
  name: string
  description: string
  light: Record<string, string>
  dark: Record<string, string>
}

export const palettes: Palette[] = [
  {
    id: 1,
    name: 'Warm Terracotta',
    description: 'Earthy, warm, inviting',
    light: {
      '--background': 'oklch(0.98 0.01 45)',
      '--foreground': 'oklch(0.25 0.05 45)',
      '--primary': 'oklch(0.45 0.12 35)',
      '--primary-foreground': 'oklch(0.98 0.01 45)',
      '--muted': 'oklch(0.95 0.02 50)',
      '--muted-foreground': 'oklch(0.50 0.04 40)',
      '--destructive': 'oklch(0.55 0.20 25)',
      '--border': 'oklch(0.90 0.02 45)',
      '--ring': 'oklch(0.45 0.12 35)',
    },
    dark: {
      '--background': 'oklch(0.20 0.03 45)',
      '--foreground': 'oklch(0.95 0.01 50)',
      '--primary': 'oklch(0.65 0.15 35)',
      '--primary-foreground': 'oklch(0.20 0.03 45)',
      '--muted': 'oklch(0.30 0.04 45)',
      '--muted-foreground': 'oklch(0.70 0.03 50)',
      '--destructive': 'oklch(0.65 0.22 25)',
      '--border': 'oklch(0.35 0.03 45)',
      '--ring': 'oklch(0.65 0.15 35)',
    },
  },
  {
    id: 2,
    name: 'Amber Sunset',
    description: 'Bright, energetic, optimistic',
    light: {
      '--background': 'oklch(0.99 0.01 85)',
      '--foreground': 'oklch(0.20 0.02 30)',
      '--primary': 'oklch(0.60 0.18 75)',
      '--primary-foreground': 'oklch(0.99 0.01 85)',
      '--muted': 'oklch(0.96 0.02 80)',
      '--muted-foreground': 'oklch(0.45 0.05 70)',
      '--destructive': 'oklch(0.55 0.22 25)',
      '--border': 'oklch(0.92 0.02 75)',
      '--ring': 'oklch(0.60 0.18 75)',
    },
    dark: {
      '--background': 'oklch(0.15 0.02 30)',
      '--foreground': 'oklch(0.96 0.01 80)',
      '--primary': 'oklch(0.70 0.20 75)',
      '--primary-foreground': 'oklch(0.15 0.02 30)',
      '--muted': 'oklch(0.25 0.03 35)',
      '--muted-foreground': 'oklch(0.75 0.04 70)',
      '--destructive': 'oklch(0.70 0.25 25)',
      '--border': 'oklch(0.30 0.03 40)',
      '--ring': 'oklch(0.70 0.20 75)',
    },
  },
  {
    id: 3,
    name: 'Warm Neutrals',
    description: 'Sophisticated, minimal, timeless',
    light: {
      '--background': 'oklch(0.98 0.005 60)',
      '--foreground': 'oklch(0.18 0.005 60)',
      '--primary': 'oklch(0.35 0.01 55)',
      '--primary-foreground': 'oklch(0.98 0.005 60)',
      '--muted': 'oklch(0.94 0.005 60)',
      '--muted-foreground': 'oklch(0.50 0.005 60)',
      '--destructive': 'oklch(0.55 0.20 25)',
      '--border': 'oklch(0.88 0.005 60)',
      '--ring': 'oklch(0.35 0.01 55)',
    },
    dark: {
      '--background': 'oklch(0.16 0.005 60)',
      '--foreground': 'oklch(0.96 0.005 60)',
      '--primary': 'oklch(0.85 0.01 55)',
      '--primary-foreground': 'oklch(0.16 0.005 60)',
      '--muted': 'oklch(0.26 0.005 60)',
      '--muted-foreground': 'oklch(0.72 0.005 60)',
      '--destructive': 'oklch(0.65 0.22 25)',
      '--border': 'oklch(0.32 0.005 60)',
      '--ring': 'oklch(0.85 0.01 55)',
    },
  },
  {
    id: 4,
    name: 'Peach Blush',
    description: 'Soft, gentle, approachable',
    light: {
      '--background': 'oklch(0.99 0.015 70)',
      '--foreground': 'oklch(0.25 0.03 25)',
      '--primary': 'oklch(0.55 0.12 50)',
      '--primary-foreground': 'oklch(0.99 0.015 70)',
      '--muted': 'oklch(0.96 0.02 65)',
      '--muted-foreground': 'oklch(0.48 0.04 40)',
      '--destructive': 'oklch(0.58 0.20 25)',
      '--border': 'oklch(0.91 0.02 60)',
      '--ring': 'oklch(0.55 0.12 50)',
    },
    dark: {
      '--background': 'oklch(0.22 0.02 25)',
      '--foreground': 'oklch(0.94 0.01 70)',
      '--primary': 'oklch(0.68 0.15 50)',
      '--primary-foreground': 'oklch(0.22 0.02 25)',
      '--muted': 'oklch(0.32 0.03 30)',
      '--muted-foreground': 'oklch(0.72 0.03 55)',
      '--destructive': 'oklch(0.68 0.23 25)',
      '--border': 'oklch(0.38 0.02 35)',
      '--ring': 'oklch(0.68 0.15 50)',
    },
  },
  {
    id: 5,
    name: 'Ocean Breeze',
    description: 'Calm, refreshing, professional',
    light: {
      '--background': 'oklch(0.99 0.01 220)',
      '--foreground': 'oklch(0.20 0.02 240)',
      '--primary': 'oklch(0.50 0.15 220)',
      '--primary-foreground': 'oklch(0.99 0.01 220)',
      '--muted': 'oklch(0.95 0.02 225)',
      '--muted-foreground': 'oklch(0.45 0.05 230)',
      '--destructive': 'oklch(0.55 0.20 25)',
      '--border': 'oklch(0.90 0.02 220)',
      '--ring': 'oklch(0.50 0.15 220)',
      '--gradient-from': '#dff2f4',
      '--gradient-to': '#1ca4ac',
      '--chat-background': 'oklch(0.9916 0.005 228.82)',
    },
    dark: {
      '--background': 'oklch(0.18 0.02 240)',
      '--foreground': 'oklch(0.95 0.01 220)',
      '--primary': 'oklch(0.65 0.18 220)',
      '--primary-foreground': 'oklch(0.18 0.02 240)',
      '--muted': 'oklch(0.28 0.03 235)',
      '--muted-foreground': 'oklch(0.70 0.04 225)',
      '--destructive': 'oklch(0.65 0.22 25)',
      '--border': 'oklch(0.33 0.02 230)',
      '--ring': 'oklch(0.65 0.18 220)',
    },
  },
  {
    id: 6,
    name: 'Deep Purple',
    description: 'Creative, modern, distinctive',
    light: {
      '--background': 'oklch(0.98 0.01 300)',
      '--foreground': 'oklch(0.22 0.03 290)',
      '--primary': 'oklch(0.55 0.20 300)',
      '--primary-foreground': 'oklch(0.98 0.01 300)',
      '--muted': 'oklch(0.94 0.02 305)',
      '--muted-foreground': 'oklch(0.48 0.05 295)',
      '--destructive': 'oklch(0.55 0.20 25)',
      '--border': 'oklch(0.89 0.02 300)',
      '--ring': 'oklch(0.55 0.20 300)',
    },
    dark: {
      '--background': 'oklch(0.20 0.02 290)',
      '--foreground': 'oklch(0.95 0.01 300)',
      '--primary': 'oklch(0.70 0.22 300)',
      '--primary-foreground': 'oklch(0.20 0.02 290)',
      '--muted': 'oklch(0.30 0.03 295)',
      '--muted-foreground': 'oklch(0.72 0.04 300)',
      '--destructive': 'oklch(0.65 0.22 25)',
      '--border': 'oklch(0.35 0.02 295)',
      '--ring': 'oklch(0.70 0.22 300)',
    },
  },
  {
    id: 7,
    name: 'Forest Green',
    description: 'Natural, balanced, grounded',
    light: {
      '--background': 'oklch(0.98 0.01 140)',
      '--foreground': 'oklch(0.20 0.02 150)',
      '--primary': 'oklch(0.45 0.12 140)',
      '--primary-foreground': 'oklch(0.98 0.01 140)',
      '--muted': 'oklch(0.94 0.02 145)',
      '--muted-foreground': 'oklch(0.46 0.04 142)',
      '--destructive': 'oklch(0.55 0.20 25)',
      '--border': 'oklch(0.89 0.02 140)',
      '--ring': 'oklch(0.45 0.12 140)',
    },
    dark: {
      '--background': 'oklch(0.18 0.02 150)',
      '--foreground': 'oklch(0.95 0.01 140)',
      '--primary': 'oklch(0.60 0.15 140)',
      '--primary-foreground': 'oklch(0.18 0.02 150)',
      '--muted': 'oklch(0.28 0.03 145)',
      '--muted-foreground': 'oklch(0.70 0.04 142)',
      '--destructive': 'oklch(0.65 0.22 25)',
      '--border': 'oklch(0.33 0.02 142)',
      '--ring': 'oklch(0.60 0.15 140)',
    },
  },
  {
    id: 8,
    name: 'Minimal Gray',
    description: 'Clean, professional, versatile',
    light: {
      '--background': 'oklch(1 0 0)',
      '--foreground': 'oklch(0.15 0 0)',
      '--primary': 'oklch(0.25 0 0)',
      '--primary-foreground': 'oklch(0.98 0 0)',
      '--muted': 'oklch(0.96 0 0)',
      '--muted-foreground': 'oklch(0.50 0 0)',
      '--destructive': 'oklch(0.55 0.20 25)',
      '--border': 'oklch(0.90 0 0)',
      '--ring': 'oklch(0.25 0 0)',
    },
    dark: {
      '--background': 'oklch(0.12 0 0)',
      '--foreground': 'oklch(0.98 0 0)',
      '--primary': 'oklch(0.90 0 0)',
      '--primary-foreground': 'oklch(0.12 0 0)',
      '--muted': 'oklch(0.22 0 0)',
      '--muted-foreground': 'oklch(0.70 0 0)',
      '--destructive': 'oklch(0.65 0.22 25)',
      '--border': 'oklch(0.28 0 0)',
      '--ring': 'oklch(0.90 0 0)',
    },
  },
  {
    id: 9,
    name: 'High Contrast',
    description: 'Bold, accessible, readable',
    light: {
      '--background': 'oklch(1 0 0)',
      '--foreground': 'oklch(0.10 0 0)',
      '--primary': 'oklch(0.20 0 0)',
      '--primary-foreground': 'oklch(1 0 0)',
      '--muted': 'oklch(0.94 0 0)',
      '--muted-foreground': 'oklch(0.40 0 0)',
      '--destructive': 'oklch(0.50 0.22 25)',
      '--border': 'oklch(0.85 0 0)',
      '--ring': 'oklch(0.20 0 0)',
    },
    dark: {
      '--background': 'oklch(0.08 0 0)',
      '--foreground': 'oklch(0.99 0 0)',
      '--primary': 'oklch(0.95 0 0)',
      '--primary-foreground': 'oklch(0.08 0 0)',
      '--muted': 'oklch(0.18 0 0)',
      '--muted-foreground': 'oklch(0.80 0 0)',
      '--destructive': 'oklch(0.70 0.25 25)',
      '--border': 'oklch(0.25 0 0)',
      '--ring': 'oklch(0.95 0 0)',
    },
  },
  {
    id: 10,
    name: 'Vibrant Modern',
    description: 'Energetic, contemporary, eye-catching',
    light: {
      '--background': 'oklch(0.99 0.01 120)',
      '--foreground': 'oklch(0.18 0.03 280)',
      '--primary': 'oklch(0.55 0.22 15)',
      '--primary-foreground': 'oklch(0.99 0.01 120)',
      '--muted': 'oklch(0.95 0.02 100)',
      '--muted-foreground': 'oklch(0.45 0.05 280)',
      '--destructive': 'oklch(0.55 0.20 25)',
      '--border': 'oklch(0.88 0.02 110)',
      '--ring': 'oklch(0.55 0.22 15)',
    },
    dark: {
      '--background': 'oklch(0.16 0.02 280)',
      '--foreground': 'oklch(0.96 0.01 120)',
      '--primary': 'oklch(0.70 0.25 15)',
      '--primary-foreground': 'oklch(0.16 0.02 280)',
      '--muted': 'oklch(0.26 0.03 270)',
      '--muted-foreground': 'oklch(0.75 0.04 290)',
      '--destructive': 'oklch(0.65 0.22 25)',
      '--border': 'oklch(0.32 0.02 275)',
      '--ring': 'oklch(0.70 0.25 15)',
    },
  },
]

export function applyPalette(paletteId: number) {
  if (typeof window === 'undefined') return
  
  const palette = palettes.find((p) => p.id === paletteId)
  if (!palette) return

  const root = document.documentElement

  // Clear previous palette variables to prevent leakage between palettes
  Array.from(root.style)
    .filter((name) => name.startsWith('--p-light-') || name.startsWith('--p-dark-'))
    .forEach((name) => root.style.removeProperty(name))

  // Set light variables
  Object.entries(palette.light).forEach(([property, value]) => {
    // --background -> --p-light-background
    const name = `--p-light-${property.slice(2)}`
    root.style.setProperty(name, value)
  })

  // Set dark variables
  Object.entries(palette.dark).forEach(([property, value]) => {
    // --background -> --p-dark-background
    const name = `--p-dark-${property.slice(2)}`
    root.style.setProperty(name, value)
  })

  localStorage.setItem('palette', paletteId.toString())
}

export function initPalette() {
  if (typeof window === 'undefined') return
  
  const stored = localStorage.getItem('palette')
  const paletteId = stored ? parseInt(stored, 10) : 5

  if (paletteId && palettes.find((p) => p.id === paletteId)) {
    applyPalette(paletteId)
  }
}
