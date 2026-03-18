import { StrictMode } from "react"
import { createRoot } from "react-dom/client"

import "./index.css"
import App from "./App.tsx"
import { ThemeProvider } from "@/components/theme-provider.tsx"
import { TooltipProvider } from "@/components/ui/tooltip"
import { LocaleProvider } from "@/features/classic-chat/locale-context"
import { SessionProvider } from "@/features/classic-chat/session-context"

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ThemeProvider storageKey="classic-chat-theme" defaultTheme="light">
      <TooltipProvider>
        <LocaleProvider>
          <SessionProvider>
            <App />
          </SessionProvider>
        </LocaleProvider>
      </TooltipProvider>
    </ThemeProvider>
  </StrictMode>
)
