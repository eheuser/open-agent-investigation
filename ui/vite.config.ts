import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173, // Note: Port 443 requires root/admin privileges. Use 5173 for dev, 443 in production
    https: {
      key: './certs/server.key',
      cert: './certs/server.crt',
    },
    proxy: {
      '/api': {
        target: 'http://api:8000',
        changeOrigin: true,
        secure: false
      },
      '/ws': {
        target: 'ws://api:8000',
        ws: true
      }
    }
  }
});
