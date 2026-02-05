import React from "react"
import { palettes } from "@/lib/themes"

export function PaletteScript() {
  // We only need id, light and dark properties for the script
  const minimalPalettes = palettes.map(p => ({
    id: p.id,
    light: p.light,
    dark: p.dark
  }))

  const scriptContent = `
    (function() {
      try {
        const palettes = ${JSON.stringify(minimalPalettes)};
        const stored = localStorage.getItem('palette');
        const id = stored ? parseInt(stored, 10) : 5;
        const palette = palettes.find(p => p.id === id) || palettes.find(p => p.id === 5) || palettes[0];
        const root = document.documentElement;
        
        Object.entries(palette.light).forEach(([k, v]) => {
          root.style.setProperty('--p-light-' + k.slice(2), v);
        });
        Object.entries(palette.dark).forEach(([k, v]) => {
          root.style.setProperty('--p-dark-' + k.slice(2), v);
        });
      } catch (e) {
        console.error('Palette script error:', e);
      }
    })();
  `

  return (
    <script
      dangerouslySetInnerHTML={{ __html: scriptContent }}
    />
  )
}
