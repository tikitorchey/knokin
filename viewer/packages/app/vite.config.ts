import { defineConfig } from 'vitest/config';
import { fileURLToPath } from 'node:url';

const core = fileURLToPath(new URL('../core/src/index.ts', import.meta.url));

export default defineConfig({
  base: './',
  resolve: { alias: { '@knokin/core': core } },
  build: { target: 'es2022', outDir: 'dist' },
  server: { host: true },
  test: { environment: 'node', include: ['test/**/*.test.ts'] },
});
