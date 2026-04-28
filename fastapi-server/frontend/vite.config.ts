import { defineConfig } from 'vite'

export default defineConfig({
  build: {
    outDir: '../static',
    emptyOutDir: false,
    rollupOptions: {
      input: {
        dashboard: './src/dashboard.ts',
        triage: './src/triage.ts',
        runDetail: './src/run-detail.ts',
      },
      output: {
        entryFileNames: '[name].js',
        chunkFileNames: '[name].js',
        manualChunks: {
          vendor: ['chart.js'],
        },
      },
    },
    minify: true,
  },
})
