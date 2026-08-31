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
  resolve: {
    alias: { '@': webRoot },
    // Keep the large ONNX WebAssembly binary in public assets instead of
    // embedding a second runtime copy in the JavaScript bundle.
    conditions: ['onnxruntime-web-use-extern-wasm'],
  },
  define: {
    'process.env.NEXT_PUBLIC_API_URL': JSON.stringify(
      process.env.NEXT_PUBLIC_API_URL ?? '',
    ),
    'process.env.NEXT_PUBLIC_PLAY_RUNTIME': JSON.stringify(
      process.env.NEXT_PUBLIC_PLAY_RUNTIME ?? 'browser',
    ),
    'process.env.NODE_ENV': JSON.stringify(
      process.env.NODE_ENV ?? 'production',
    ),
  },
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
