import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { fileURLToPath, URL } from 'node:url';
import { cpSync, existsSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { gzipSync } from 'node:zlib';
import { resolve, join } from 'node:path';

const backendPort = Number(process.env.ARC_WEB_PORT || '3000');

function copyPdfCmaps() {
  let outDir;
  return {
    name: 'copy-pdf-cmaps',
    configResolved(config) {
      outDir = resolve(config.root, config.build.outDir);
    },
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
        join(outDir, 'pdfjs-cmaps'),
        {
          recursive: true,
        },
      );
    },
  };
}

function precompressAssets() {
  let outDir;
  return {
    name: 'precompress-assets',
    configResolved(config) {
      outDir = resolve(config.root, config.build.outDir);
    },
    closeBundle() {
      const assets = join(outDir, 'assets');
      if (!existsSync(assets)) return;
      for (const name of readdirSync(assets)) {
        if (!/\.(?:m?js|css)$/.test(name)) continue;
        const content = readFileSync(join(assets, name));
        if (content.length > 1024) writeFileSync(join(assets, name + '.gz'), gzipSync(content, { level: 9 }));
      }
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
  plugins: [react(), tailwindcss(), copyPdfCmaps(), precompressAssets()],
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
