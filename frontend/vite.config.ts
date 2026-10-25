import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, fileURLToPath(new URL('.', import.meta.url)), '');
  const target = env.API_PROXY_TARGET || 'http://127.0.0.1:8000';
  const proxy = { '/api': { target, changeOrigin: true }, '/health': { target, changeOrigin: true } };
  return {
    plugins: [react()],
    server: { host: '127.0.0.1', port: 5173, strictPort: true, proxy },
    preview: { host: '127.0.0.1', proxy },
    build: {
      rolldownOptions: {
        output: {
          codeSplitting: {
            groups: [
              { name: 'react', test: /node_modules[\\/](?:react|react-dom|scheduler)[\\/]/ },
              { name: 'alfa', test: /node_modules[\\/]@alfalab[\\/]/ },
            ],
          },
        },
      },
    },
  };
});
