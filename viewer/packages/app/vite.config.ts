import { defineConfig } from 'vitest/config';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const core = fileURLToPath(new URL('../core/src/index.ts', import.meta.url));

const appVersion = readFileSync(fileURLToPath(new URL('../../../VERSION', import.meta.url)), 'utf8').trim();

export default defineConfig({
  base: './',
  define: { __APP_VERSION__: JSON.stringify(appVersion) },
  resolve: { alias: { '@knokin/core': core } },
  build: { target: 'es2022', outDir: 'dist' },
  server: { host: true },
  test: { environment: 'node', include: ['test/**/*.test.ts'] },
});
