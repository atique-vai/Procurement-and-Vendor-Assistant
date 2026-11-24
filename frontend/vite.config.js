import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const backendTarget = "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  css: {
    postcss: {
      plugins: [],
    },
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      "/chat": backendTarget,
      "/approvals": backendTarget,
      "/graph": backendTarget,
      "/health": backendTarget,
    },
  },
});