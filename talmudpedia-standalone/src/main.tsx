import { StrictMode } from "react"
import { createRoot } from "react-dom/client"

import "./index.css"
import App from "./App.tsx"
import { ThemeProvider } from "@/components/theme-provider.tsx"
import { TooltipProvider } from "@/components/ui/tooltip"
import { SessionProvider } from "@/features/classic-chat/session-context"

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ThemeProvider storageKey="classic-chat-theme" defaultTheme="light">
      <TooltipProvider>
        <SessionProvider>
          <App />
        </SessionProvider>
      </TooltipProvider>
    </ThemeProvider>
  </StrictMode>
)
