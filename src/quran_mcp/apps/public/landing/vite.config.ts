import { svelte } from "@sveltejs/vite-plugin-svelte";
import { defineConfig } from "vite";
import { viteSingleFile } from "vite-plugin-singlefile";

export default defineConfig({
  plugins: [svelte(), viteSingleFile()],
  build: {
    outDir: "../../../assets",
    emptyOutDir: false,
    rollupOptions: {
      input: "landing.html",
      output: { entryFileNames: "[name].js" },
    },
  },
});
