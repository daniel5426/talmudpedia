export const themes = [
  {
    name: "default",
    label: "Default",
    activeColor: "oklch(0.205 0 0)",
  },
  {
    name: "blue",
    label: "Blue",
    activeColor: "oklch(0.488 0.243 264.376)",
  },
  {
    name: "rose",
    label: "Rose",
    activeColor: "oklch(0.577 0.245 27.325)",
  },
  {
    name: "green",
    label: "Green",
    activeColor: "oklch(0.511 0.162 143.311)",
  },
  {
    name: "orange",
    label: "Orange",
    activeColor: "oklch(0.646 0.222 41.116)",
  },
] as const

export type Theme = (typeof themes)[number]
