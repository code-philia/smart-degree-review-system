import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { fileURLToPath, URL } from 'node:url';
import { cpSync, existsSync, readFileSync } from 'node:fs';

const backendPort = Number(process.env.ARC_WEB_PORT || '3000');

function copyPdfCmaps() {
  return {
    name: 'copy-pdf-cmaps',
    configureServer(server) {
      server.middlewares.use('/pdfjs-cmaps', (request, response, next) => {
        const fileName = request.url?.split('?')[0].replace(/^\/+/, '') || '';
        if (!/^[A-Za-z0-9_-]+\.bcmap$/.test(fileName)) return next();
        const source = new URL(`./node_modules/pdfjs-dist/cmaps/${fileName}`, import.meta.url);
        if (!existsSync(source)) return next();
        response.setHeader('Content-Type', 'application/octet-stream');
        response.end(readFileSync(source));
      });
    },
    closeBundle() {
      cpSync(
        new URL('./node_modules/pdfjs-dist/cmaps/', import.meta.url),
        new URL('./dist/pdfjs-cmaps/', import.meta.url),
        {
          recursive: true,
        },
      );
    },
  };
}

// https://vite.dev/config/
export default defineConfig({
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  plugins: [react(), tailwindcss(), copyPdfCmaps()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './test/setup.ts',
    include: ['tests/**/*.{test,spec}.{js,jsx,ts,tsx}'],
  },
  server: {
    proxy: {
      '/api': `http://127.0.0.1:${backendPort}`,
    },
  },
});
