import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import basicSsl from '@vitejs/plugin-basic-ssl';

export default defineConfig({
  base: '/trading/',
  plugins: [react(), basicSsl()],
  build: {
    chunkSizeWarningLimit: 1000,
  },
  server: {
    port: 5174,
    host: '127.0.0.1',
    proxy: {
      '/api/owner/v1': {
        target: 'https://jiaoyingpan.cloud',
        changeOrigin: true,
        secure: true,
      },
    },
  },
  preview: {
    port: 5174,
    host: '127.0.0.1',
    proxy: {
      '/api/owner/v1': {
        target: 'https://jiaoyingpan.cloud',
        changeOrigin: true,
        secure: true,
      },
    },
  },
});

