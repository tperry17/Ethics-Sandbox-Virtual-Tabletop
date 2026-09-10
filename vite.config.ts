import { defineConfig } from "vite";

export default defineConfig({
  build: {
    emptyOutDir: true,
    outDir: "static/table",
    rollupOptions: {
      input: "client/src/main.ts",
      output: {
        entryFileNames: "table.js",
      },
    },
  },
});
