import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { viteSingleFile } from "vite-plugin-singlefile";

const isStatic = process.env.VITE_STATIC === "1";

export default defineConfig({
  plugins: isStatic ? [react(), viteSingleFile()] : [react()],
  base: isStatic ? "./" : "/",
  build: isStatic ? { outDir: "dist-static", assetsInlineLimit: 100_000_000 } : {},
  server: {
    port: 5173,
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
});
