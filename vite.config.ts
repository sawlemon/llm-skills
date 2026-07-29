import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import { reportCardPlugin } from './src/data/reportCardPlugin';

export default defineConfig({
  base: '/llm-skills/',
  plugins: [react(), reportCardPlugin()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./vitest.setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
  },
});
