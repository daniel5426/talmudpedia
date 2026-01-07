"use client"

import { useEffect } from "react"
import { initPalette } from "@/lib/themes"
import { useTheme } from "next-themes"

export function PaletteInitializer() {
  useEffect(() => {
    initPalette()
  }, [])

  return null
}
