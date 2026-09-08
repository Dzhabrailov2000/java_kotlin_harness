/**
 * Build input of the original Pixel Agents frontend, as the monitor builds it.
 *
 * The root is build/webview-ui: the byte-exact vendor copy with the patches of
 * patches/ applied, never the vendor tree itself. Upstream's own config also wires a
 * Vite dev server, its React refresh plugin and a mock-asset middleware; none of that
 * takes part in a production build, and the monitor has no dev server, so only Tailwind
 * remains. JSX is compiled by the same esbuild transform Vite uses for upstream's
 * "jsx": "react-jsx" tsconfig, so the emitted components are the original ones.
 *
 * publicDir is off on purpose: the fonts, the room artwork and the raw sprite PNGs are
 * served straight from vendor/webview-ui/public at their recorded hashes instead of
 * being copied into dist, so the bytes the browser gets are provably the upstream ones.
 */

import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vite';

export default defineConfig({
  root: 'build/webview-ui',
  publicDir: false,
  plugins: [tailwindcss()],
  esbuild: { jsx: 'automatic' },
  build: { outDir: '../../dist/office', emptyOutDir: true },
  base: './',
  logLevel: 'warn',
});
