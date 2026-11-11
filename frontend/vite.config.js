import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/chat":      "[127.0.0.1](http://127.0.0.1:8000)",
      "/health":    "[127.0.0.1](http://127.0.0.1:8000)",
      "/employees": "[127.0.0.1](http://127.0.0.1:8000)",
      "/threads":   "[127.0.0.1](http://127.0.0.1:8000)",
      "/evaluation": "[127.0.0.1](http://127.0.0.1:8000)",
    },
  },
});
