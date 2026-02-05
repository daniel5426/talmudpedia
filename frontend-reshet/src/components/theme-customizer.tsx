"use client"

import * as React from "react"
import { Check, Moon, Sun, Palette } from "lucide-react"
import { useTheme } from "next-themes"

import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { palettes, applyPalette } from "@/lib/themes"
import { useDirection } from "@/components/direction-provider"

export function ThemeCustomizer() {
  const { theme, setTheme } = useTheme()
  const [mounted, setMounted] = React.useState(false)
  const [activePaletteId, setActivePaletteId] = React.useState<number | null>(null)
  const { direction } = useDirection()

  React.useEffect(() => {
    setMounted(true)
    const stored = localStorage.getItem('palette')
    if (stored) {
      setActivePaletteId(parseInt(stored, 10))
    } else {
      setActivePaletteId(5)
    }
  }, [])

  // Re-apply palette when activePaletteId changes
  React.useEffect(() => {
    if (activePaletteId) {
      applyPalette(activePaletteId)
    }
  }, [activePaletteId])

  const handlePaletteChange = (paletteId: number) => {
    setActivePaletteId(paletteId)
    applyPalette(paletteId)
  }

  if (!mounted) {
    return (
      <Button variant="ghost" size="icon" className="h-9 w-9">
        <Palette className="h-4 w-4" />
        <span className="sr-only">Customize theme</span>
      </Button>
    )
  }

  return (
    <DropdownMenu dir={direction}>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" className="h-9 w-9">
          <Palette className="h-4 w-4" />
          <span className="sr-only">Customize theme</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-48">
        <DropdownMenuLabel>Color Palette</DropdownMenuLabel>
        <DropdownMenuSeparator />
        <div className="max-h-60 overflow-y-auto">
          {palettes.map((p) => (
            <DropdownMenuItem
              key={p.id}
              onClick={() => handlePaletteChange(p.id)}
              className="flex items-center justify-between py-2"
            >
              <div className="flex flex-col gap-0.5">
                <div className="flex items-center gap-2">
                  <div
                    className="h-3 w-3 rounded-full border"
                    style={{ backgroundColor: p.light['--primary'] }}
                  />
                  <span className="text-sm font-medium">{p.name}</span>
                </div>
                <span className="text-[10px] text-muted-foreground line-clamp-1">{p.description}</span>
              </div>
              {activePaletteId === p.id && <Check className="h-4 w-4 ml-2" />}
            </DropdownMenuItem>
          ))}
        </div>
        <DropdownMenuSeparator />
        <DropdownMenuLabel>Mode</DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={() => setTheme("light")}>
          <Sun className="mr-2 h-4 w-4" />
          Light
          {theme === "light" && <Check className="ml-auto h-4 w-4" />}
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => setTheme("dark")}>
          <Moon className="mr-2 h-4 w-4" />
          Dark
          {theme === "dark" && <Check className="ml-auto h-4 w-4" />}
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => setTheme("system")}>
          <span className="mr-2">💻</span>
          System
          {theme === "system" && <Check className="ml-auto h-4 w-4" />}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
