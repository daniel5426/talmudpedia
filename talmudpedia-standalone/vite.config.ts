import path from "path"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

const usePolling = process.env.__APPS_VITE_USE_POLLING === "1"
const pollingInterval = Number(process.env.__APPS_VITE_POLL_INTERVAL_MS || 250)
const devApiTarget = process.env.VITE_DEV_API_TARGET || "http://127.0.0.1:3001"

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  base: "./",
  server:
    usePolling || devApiTarget
      ? {
          proxy: {
            "/api": {
              target: devApiTarget,
              changeOrigin: true,
            },
          },
          ...(usePolling
            ? {
        watch: {
          usePolling: true,
          interval: Number.isFinite(pollingInterval) ? pollingInterval : 250,
        },
              }
            : {}),
        }
      : undefined,
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
})
