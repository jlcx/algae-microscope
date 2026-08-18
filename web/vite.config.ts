import { defineConfig } from 'vite';

export default defineConfig({
  server: {
    proxy: {
      // dev-mode proxy to the algae-microscope server (§6.1: the web app
      // talks only to the server)
      '/api': 'http://127.0.0.1:8321',
    },
  },
  build: { outDir: 'dist' },
});
