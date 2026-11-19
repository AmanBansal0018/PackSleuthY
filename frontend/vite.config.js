import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Requests to /api are forwarded to the FastAPI server during development.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
});
