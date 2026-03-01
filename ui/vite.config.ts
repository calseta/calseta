import path from "path"
import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"
import tailwindcss from "@tailwindcss/vite"

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ["react", "react-dom"],
          router: ["@tanstack/react-router"],
          query: ["@tanstack/react-query"],
          charts: ["recharts"],
        },
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/v1": "http://localhost:8000",
      "/health": "http://localhost:8000",
      "/docs": "http://localhost:8000",
      "/openapi.json": "http://localhost:8000",
    },
  },
})
