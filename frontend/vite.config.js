import { defineConfig } from "vite";

export default defineConfig({
  server: {
    proxy: {
      "/auth": "http://127.0.0.1:8000",
      "/expected_points": "http://127.0.0.1:8000",
      "/bootstrap_dynamic_entry_set": "http://127.0.0.1:8000",
      "/health": "http://127.0.0.1:8000",
    },
  },
});
