import { createRequire } from 'node:module';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { afterAll, afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const require = createRequire(import.meta.url);
const fs = require('node:fs/promises');
const { getReferenceCredentials, getReferenceSettings } = require('../src/auth/referenceSettingsService');
const { createTestDatabaseHarness } = require('../src/database');
const envKeys = ['OPENALEX_API_KEYS', 'OPENALEX_API_KEY', 'PAPER_COMPILER_EVIDENCE_CONFIG'];
const originalEnv = Object.fromEntries(envKeys.map(key => [key, process.env[key]]));
let directory, configPath;
const modes = new Map();

async function writeConfig(content, mode = 0o600) {
  await fs.writeFile(configPath, content, { mode });
  await fs.chmod(configPath, mode);
  modes.set(configPath, mode);
}

// Windows exposes Unix permissions as 0666 even for files created with0600.
// Keep contents, file handles, symlinks and missing-path behavior real, while
// supplying the POSIX permission bits that the deployment's Linux fs returns.
function usePosixFixturePermissionsOnWindows() {
  if (process.platform !== 'win32') return;
  const lstat = fs.lstat.bind(fs), open = fs.open.bind(fs);
  function withMode(info, filename) {
    if (modes.has(String(filename))) info.mode = (info.mode & ~0o777) | modes.get(String(filename));
    return info;
  }
  vi.spyOn(fs, 'lstat').mockImplementation(async (filename, ...args) => withMode(await lstat(filename, ...args), filename));
  vi.spyOn(fs, 'open').mockImplementation(async (filename, ...args) => {
    const handle = await open(filename, ...args);
    const stat = handle.stat.bind(handle);
    handle.stat = async (...statArgs) => withMode(await stat(...statArgs), filename);
    return handle;
  });
}

describe('private legacy OpenAlex platform credentials', () => {
  beforeEach(async () => {
    for (const key of envKeys) delete process.env[key];
    directory = await fs.mkdtemp(path.join(tmpdir(), 'reference-platform-'));
    configPath = path.join(directory, 'evidence.env');
    process.env.PAPER_COMPILER_EVIDENCE_CONFIG = configPath;
    modes.clear();
    usePosixFixturePermissionsOnWindows();
  });
  afterEach(async () => {
    vi.restoreAllMocks();
    await fs.rm(directory, { recursive: true, force: true });
  });
  afterAll(() => {
    for (const key of envKeys) {
      if (originalEnv[key] === undefined) delete process.env[key]; else process.env[key] = originalEnv[key];
    }
  });

  it('loads all deduplicated legacy keys from an owner-private file without exposing unrelated settings', async () => {
    await writeConfig('# private evidence settings\nOTHER_SECRET=unrelated-secret\nOPENALEX_API_KEYS="legacy-one, legacy-two,legacy-three,legacy-one"\n');
    const credentials = await getReferenceCredentials();
    expect(credentials.platformKeys).toEqual(['legacy-one', 'legacy-two', 'legacy-three']);
    expect(JSON.stringify(credentials)).not.toContain('unrelated-secret');
    expect(credentials.personalKey).toBeNull();
    expect(credentials.serpapiKey).toBeNull();
  });

  it('accepts read-only owner-private files and the singular legacy variable', async () => {
    await writeConfig("OPENALEX_API_KEY='legacy-single'\n", 0o400);
    expect((await getReferenceCredentials()).platformKeys).toEqual(['legacy-single']);
  });

  it('keeps defined environment settings authoritative and does not fall back for explicit blanks', async () => {
    await writeConfig('OPENALEX_API_KEYS=private-file-one,private-file-two\n');
    process.env.OPENALEX_API_KEY = 'environment-single';
    expect((await getReferenceCredentials()).platformKeys).toEqual(['environment-single']);
    process.env.OPENALEX_API_KEYS = 'environment-one,environment-two,environment-one';
    expect((await getReferenceCredentials()).platformKeys).toEqual(['environment-one', 'environment-two']);
    process.env.OPENALEX_API_KEYS = '';
    expect((await getReferenceCredentials()).platformKeys).toEqual([]);
    delete process.env.OPENALEX_API_KEYS;
    process.env.OPENALEX_API_KEY = '';
    expect((await getReferenceCredentials()).platformKeys).toEqual([]);
    process.env.OPENALEX_API_KEY = '   ';
    expect((await getReferenceCredentials()).platformKeys).toEqual([]);
    delete process.env.OPENALEX_API_KEY;
    expect((await getReferenceCredentials()).platformKeys).toEqual(['private-file-one', 'private-file-two']);
  });

  it('rejects group or world access instead of reading platform secrets', async () => {
    for (const mode of [0o640, 0o604, 0o644, 0o777]) {
      await writeConfig('OPENALEX_API_KEY=must-stay-private\n', mode);
      expect((await getReferenceCredentials()).platformKeys).toEqual([]);
    }
  });

  it('rejects symlink and directory config paths without throwing raw filesystem errors', async () => {
    const target = path.join(directory, 'real-config');
    if (process.platform === 'win32') {
      await fs.mkdir(target);
      await fs.symlink(target, configPath, 'junction');
    } else {
      await fs.writeFile(target, 'OPENALEX_API_KEY=symlink-secret', { mode: 0o600 });
      await fs.symlink(target, configPath);
    }
    expect((await getReferenceCredentials()).platformKeys).toEqual([]);
    await fs.unlink(configPath);
    await fs.mkdir(configPath);
    expect((await getReferenceCredentials()).platformKeys).toEqual([]);
  });

  it('rejects malformed, ambiguous or oversized config while leaving no-key fallback usable', async () => {
    for (const value of [
      'OPENALEX_API_KEYS="unterminated-key\n',
      'OPENALEX_API_KEY=invalid token with spaces\n',
      'OPENALEX_API_KEY=valid-key\nOPENALEX_API_KEY=duplicate-assignment\n',
      'OPENALEX_API_KEYS=' + Array.from({ length: 9 }, (_, i) => `key-${i}`).join(','),
      'OPENALEX_API_KEY=' + 'x'.repeat(513),
      'OPENALEX_API_KEY=one,key!invalid\n',
      'OPENALEX_API_KEY=valid-key\nUNRELATED=' + 'x'.repeat(65536),
    ]) {
      await writeConfig(value);
      expect((await getReferenceCredentials()).platformKeys).toEqual([]);
    }
    await fs.unlink(configPath);
    expect((await getReferenceCredentials()).platformKeys).toEqual([]);
  });

  it('does not add platform keys, filenames or platform status to public account settings', async () => {
    await writeConfig('OPENALEX_API_KEYS=private-file-one,private-file-two\n');
    expect((await getReferenceCredentials()).platformKeys).toEqual(['private-file-one', 'private-file-two']);
    const harness = createTestDatabaseHarness({ label: 'reference-platform-public-boundary' });
    await harness.setup();
    try {
      const status = await getReferenceSettings('jaccount:unconfigured');
      expect(Object.keys(status).sort()).toEqual(['can_verify_references', 'configured', 'key_hint', 'serpapi_configured', 'serpapi_key_hint', 'storage_available']);
      expect(status.can_verify_references).toBe(false);
      expect(status.configured).toBe(false);
      expect(status.key_hint).toBeNull();
      expect(JSON.stringify(status)).not.toContain('private-file');
      expect(JSON.stringify(status)).not.toContain(configPath);
    } finally {
      await harness.cleanup();
    }
  });
});
