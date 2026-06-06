import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The dashboard is served by FastAPI at /app/* in production (built into
// cockpit/static/dashboard). In dev it runs on :5173 and proxies /api → :8765.
export default defineConfig({
  plugins: [react()],
  base: "/app/",
  build: {
    outDir: "../cockpit/static/dashboard",
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://127.0.0.1:8765", changeOrigin: true },
      "/oauth": { target: "http://127.0.0.1:8765", changeOrigin: true },
    },
  },
});
