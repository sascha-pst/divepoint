import { defineConfig } from "vite";

export default defineConfig({
  server: {
    proxy: { "/v1": process.env.DIVEPOINT_API_URL || "http://127.0.0.1:8000" },
  },
});
