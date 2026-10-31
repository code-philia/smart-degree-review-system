import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { fileURLToPath, URL } from 'node:url';
import { cpSync, existsSync, readFileSync, readdirSync, writeFileSync, realpathSync } from 'node:fs';
import { gzipSync } from 'node:zlib';
import { resolve, join } from 'node:path';

const backendPort = Number(process.env.ARC_WEB_PORT || '3000');

function copyPdfResources() {
  const packageRoot = fileURLToPath(new URL('./node_modules/pdfjs-dist/', import.meta.url));
  const { version } = JSON.parse(readFileSync(join(packageRoot, 'package.json'), 'utf8'));
  const resources = ['cmaps', 'standard_fonts', 'wasm'];
  let outDir;
  return {
    name: 'copy-pdf-resources',
    configResolved(config) { outDir = resolve(config.root, config.build.outDir); },
    configureServer(server) {
      function serveResource(resource, fileName, response, next) {
        if (!resources.includes(resource) || !/^[A-Za-z0-9_-][A-Za-z0-9_.-]*$/.test(fileName)) return next();
        const source = join(packageRoot, resource, fileName);
        if (!existsSync(source)) return next();
        const mime = fileName.endsWith('.js') ? 'application/javascript' : fileName.endsWith('.wasm') ? 'application/wasm' : fileName.endsWith('.ttf') ? 'font/ttf' : fileName.endsWith('.otf') ? 'font/otf' : 'application/octet-stream';
        response.setHeader('Content-Type', mime);
        response.end(readFileSync(source));
      }
      server.middlewares.use(`/pdfjs-resources/${version}/`, (request, response, next) => {
        const [resource, fileName, extra] = (request.url?.split('?')[0].replace(/^\/+/, '') || '').split('/');
        if (extra || !fileName) return next();
        serveResource(resource, fileName, response, next);
      });
      server.middlewares.use('/pdfjs-cmaps', (request, response, next) => {
        serveResource('cmaps', request.url?.split('?')[0].replace(/^\/+/, '') || '', response, next);
      });
    },
    closeBundle() {
      for (const resource of resources) cpSync(join(packageRoot, resource), join(outDir, 'pdfjs-resources', version, resource), { recursive: true });
      // Keep already-open tabs that reference the previous CMap path working.
      cpSync(join(packageRoot, 'cmaps'), join(outDir, 'pdfjs-cmaps'), { recursive: true });
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
  plugins: [react(), tailwindcss(), copyPdfResources(), precompressAssets()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './test/setup.ts',
    include: ['tests/**/*.{test,spec}.{js,jsx,ts,tsx}'],
  },
  server: {
    fs: { allow: [fileURLToPath(new URL('.', import.meta.url)), realpathSync(fileURLToPath(new URL('./node_modules', import.meta.url)))] },
    proxy: {
      '/api': `http://127.0.0.1:${backendPort}`,
    },
  },
});
