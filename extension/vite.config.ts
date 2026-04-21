import {
  copyFileSync,
  existsSync,
  mkdirSync,
  readdirSync,
  statSync,
} from "node:fs";
import { join, resolve } from "node:path";

import { defineConfig } from "vite";

/** Recursively copy public/ assets (popup.html, overlay.css), the MV3
 *  manifest, and icons into dist/ so Chrome can load the build unpacked. */
function copyChromeAssets() {
  const root = __dirname;
  return {
    name: "autocurb-copy-public",
    closeBundle() {
      const out = resolve(root, "dist");
      mkdirSync(out, { recursive: true });

      const copyTree = (src: string, rel: string) => {
        if (!existsSync(src)) return;
        for (const name of readdirSync(src)) {
          const full = join(src, name);
          const relPath = rel ? join(rel, name) : name;
          if (statSync(full).isDirectory()) {
            mkdirSync(join(out, relPath), { recursive: true });
            copyTree(full, relPath);
          } else {
            copyFileSync(full, join(out, relPath));
          }
        }
      };

      copyTree(resolve(root, "public"), "");

      const manifest = resolve(root, "manifest.json");
      if (existsSync(manifest)) copyFileSync(manifest, join(out, "manifest.json"));

      const icons = resolve(root, "icons");
      if (existsSync(icons)) {
        mkdirSync(join(out, "icons"), { recursive: true });
        for (const name of readdirSync(icons)) {
          copyFileSync(join(icons, name), join(out, "icons", name));
        }
      }
    },
  };
}

export default defineConfig({
  plugins: [copyChromeAssets()],
  build: {
    outDir: "dist",
    emptyOutDir: true,
    rollupOptions: {
      input: {
        background: resolve(__dirname, "src/background/index.ts"),
        "content-facebook": resolve(__dirname, "src/content/facebook.ts"),
        "content-craigslist": resolve(__dirname, "src/content/craigslist.ts"),
      },
      output: {
        entryFileNames: "[name].js",
        chunkFileNames: "[name].js",
        assetFileNames: "[name][extname]",
      },
    },
  },
});
