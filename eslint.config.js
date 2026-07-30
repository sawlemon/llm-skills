import js from '@eslint/js';
import globals from 'globals';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';
import tseslint from 'typescript-eslint';
import prettier from 'eslint-config-prettier/flat';

export default tseslint.config(
  {
    ignores: [
      '**/dist/**',
      '**/node_modules/**',
      '**/*.tsbuildinfo',
      'package-lock.json',
      'apps/report-card/src/vite-env.d.ts',
    ],
  },

  // Application + library source (browser).
  {
    files: ['apps/report-card/src/**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat['recommended-latest'],
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
    },
  },

  // Vitest test files: same rules, plus test globals (vitest runs with globals: true).
  {
    files: ['apps/report-card/src/**/*.test.{ts,tsx}', 'apps/report-card/vitest.setup.ts'],
    extends: [js.configs.recommended, tseslint.configs.recommended],
    languageOptions: {
      ecmaVersion: 2022,
      globals: { ...globals.browser, ...globals.vitest },
    },
    rules: {
      // Test-only escape hatch for fast refresh / component-export heuristics.
      'react-refresh/only-export-components': 'off',
    },
  },

  // Node-side tooling: vite config, the report-card Vite plugin, and this config file.
  {
    files: [
      'eslint.config.js',
      'apps/report-card/vite.config.ts',
      'apps/report-card/src/data/reportCardPlugin.ts',
    ],
    extends: [js.configs.recommended, tseslint.configs.recommended],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.node,
    },
  },

  // Keep ESLint out of formatting: Prettier owns stylistic decisions. Must stay last.
  prettier,
);
