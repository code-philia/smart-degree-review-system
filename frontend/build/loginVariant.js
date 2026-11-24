export function resolveLoginVariant(value, configured = 'campus') {
  const variant = value || configured;
  if (variant !== 'campus' && variant !== 'split') {
    throw new Error('VITE_LOGIN_VARIANT must be campus or split');
  }
  return variant;
}

export function loginVariantManifest(variant) {
  const source = JSON.stringify({ schema_version: 1, variant: resolveLoginVariant(variant) });
  return {
    name: 'login-variant-manifest',
    generateBundle() {
      this.emitFile({ type: 'asset', fileName: 'login-variant.json', source });
    },
    configureServer(server) {
      server.middlewares.use('/login-variant.json', (_request, response) => {
        response.setHeader('Content-Type', 'application/json');
        response.setHeader('Cache-Control', 'no-store');
        response.end(source);
      });
    },
  };
}
