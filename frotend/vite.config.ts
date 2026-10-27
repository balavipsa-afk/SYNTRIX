import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The dev server proxies /api to the FastAPI backend, so there are no CORS or port problems.
const target = "http://127.0.0.1:8000";
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": { target, changeOrigin: true } } },
  preview: { port: 4173, proxy: { "/api": { target, changeOrigin: true } } },
});
