import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/postcss';
import { resolve } from 'node:path';
import { defineConfig } from 'vite';

const webRoot = import.meta.dirname;

/** A pure client build for static hosts such as GitHub Pages. */
export default defineConfig({
  root: resolve(webRoot, 'pages'),
  base: './',
  publicDir: resolve(webRoot, 'public'),
  css: { postcss: { plugins: [tailwindcss()] } },
  plugins: [react()],
  resolve: { alias: { '@': webRoot } },
  build: {
    outDir: resolve(webRoot, 'dist/pages'),
    emptyOutDir: true,
    rollupOptions: {
      input: {
        main: resolve(webRoot, 'pages/index.html'),
        poker: resolve(webRoot, 'pages/poker/index.html'),
        backgammon: resolve(webRoot, 'pages/backgammon/index.html'),
      },
    },
  },
});
