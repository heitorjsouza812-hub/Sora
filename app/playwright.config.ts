import { defineConfig, devices } from '@playwright/test';

// Porta do Vite (padrão 5173; troque com SORA_QA_BASE). O qa/entrar.mjs lê a mesma variável.
process.env.SORA_QA_BASE ??= 'http://localhost:5173';

export default defineConfig({
  testDir: './tests/visual',
  timeout: 30_000,
  expect: {
    toHaveScreenshot: {
      maxDiffPixelRatio: 0.005,
    },
  },
  use: {
    baseURL: process.env.SORA_QA_BASE,
    colorScheme: 'dark',
    reducedMotion: 'reduce',
  },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'], browserName: 'chromium', viewport: { width: 1440, height: 900 } } },
    { name: 'mobile', use: { ...devices['iPhone 13'], browserName: 'chromium', viewport: { width: 390, height: 844 } } },
  ],
});
