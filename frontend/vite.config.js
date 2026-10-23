import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development `npm run dev` proxies API calls to Django on :8000.
export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: { output: { manualChunks: { charts: ["recharts"], react: ["react", "react-dom", "react-router-dom"] } } },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
      "/admin": "http://localhost:8000",
      "/static": "http://localhost:8000",
    },
  },
});
