import { managedProcesses } from './processes.mjs';
import { createServer } from 'node:net';
import { mkdtemp, mkdir, writeFile, rm, access, cp } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { randomUUID } from 'node:crypto';

const frontend = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const backend = path.resolve(frontend, '../backend');
async function run(root) {
  await writeFile(path.join(root, '.owned'), '5X49 E2E');
  const output = path.join(frontend, 'e2e-artifacts');
  await mkdir(output, { recursive: true });
  for (const name of ['backend.log', 'frontend.log', 'build.log']) await writeFile(path.join(output, name), '');
  const port = () => new Promise((resolve, reject) => { const s = createServer(); s.once('error', reject); s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => resolve(p)); }); });
  const backendPort = await port(), frontendPort = await port();
  // Do not forward provider keys, proxy credentials or application configuration.
  const env = Object.fromEntries(['PATH', 'HOME', 'USERPROFILE', 'SYSTEMROOT', 'TMPDIR', 'CI', 'PLAYWRIGHT_BROWSERS_PATH', 'E2E_CHROMIUM_PATH'].filter(k => process.env[k]).map(k => [k, process.env[k]]));
  Object.assign(env, { E2E_ROOT: root, E2E_TOKEN: randomUUID(),
    E2E_BACKEND: `http://127.0.0.1:${backendPort}`, E2E_BASE_URL: `http://localhost:${frontendPort}`,
    SQLITE_DB_PATH: path.join(root, 'data/library.db'), MEDIA_DIR: path.join(root, 'empty'),
    OPERATION_MANIFEST_DIR: path.join(root, 'manifests'), WATCH_LIBRARY: 'false',
    PYTHON_DOTENV_DISABLED: '1', TMDB_API_KEY: '', OPENROUTER_API_KEY: '',
    PYTHONPATH: [backend, path.join(frontend, 'e2e')].join(path.delimiter),
    UV_CACHE_DIR: path.join(root, 'uv-cache'), NEXT_TELEMETRY_DISABLED: '1',
    BACKEND_URL: `http://127.0.0.1:${backendPort}` });
  await mkdir(env.MEDIA_DIR);
  const python = path.join(backend, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
  const { start, finish, stop, ready, children } = managedProcesses(env, output);
  const backendStart = () => start(python, ['-m', 'uvicorn', 'backend:app', '--host', '127.0.0.1', '--port', String(backendPort), '--timeout-graceful-shutdown', '2'], root, 'backend.log');
  let server, restarting = false, watcher;
  let result = 1;
  for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => { for (const child of children) child.kill('SIGTERM'); });
  try {
    // Next automatically loads these files from its project directory. Refuse to
    // consume a developer's private configuration rather than editing or copying it.
    for (const name of ['.env', '.env.local', '.env.production', '.env.production.local']) {
      let exists = true;
      try { await access(path.join(frontend, name)); } catch (error) { if (error.code === 'ENOENT') exists = false; else throw error; }
      if (exists) throw Error(`E2E requires a clean frontend environment: ${name} exists`);
    }
    await access(python);
    for (const profile of ['normal', 'mixed']) await finish(start(python, [path.join(backend, 'scripts/generate_test_data.py'), '--output-dir', path.join(root, profile), '--count', profile === 'normal' ? '12' : '60', '--profile', profile, '--video-mode', 'valid'], root));
    server = backendStart();
    await ready(`${env.E2E_BACKEND}/health`, server);
    await finish(start(process.execPath, ['node_modules/next/dist/bin/next', 'build'], frontend, 'build.log'));
    const standalone = path.join(frontend, '.next/standalone');
    await cp(path.join(frontend, '.next/static'), path.join(standalone, '.next/static'), { recursive: true });
    await cp(path.join(frontend, 'public'), path.join(standalone, 'public'), { recursive: true });
    // Match NextURL's loopback hostname normalization, avoiding a self-proxy rewrite.
    env.PORT = String(frontendPort); env.HOSTNAME = 'localhost';
    const web = start(process.execPath, ['server.js'], standalone, 'frontend.log');
    await ready(`${env.E2E_BASE_URL}/api/health`, web);
    watcher = setInterval(async () => {
      if (restarting) return;
      try { await access(path.join(root, 'restart')); } catch { return; }
      restarting = true;
      try {
        await rm(path.join(root, 'restart')); await stop(server); server = backendStart();
        await ready(`${env.E2E_BACKEND}/health`, server); await writeFile(path.join(root, 'restarted'), 'ready');
      } catch (error) { await writeFile(path.join(root, 'restart-error'), String(error)); }
      finally { restarting = false; }
    }, 100);
    await finish(start(process.execPath, ['node_modules/@playwright/test/cli.js', 'test', ...process.argv.slice(2)], frontend));
    result = 0;
  } catch (error) { console.error(error); }
  finally {
    clearInterval(watcher);
    while (restarting) await new Promise(r => setTimeout(r, 100));
    await Promise.all([...children].map(stop));
  }
  return result;
}
const root = await mkdtemp(path.join(tmpdir(), '5x49-e2e-'));
try { process.exitCode = await run(root); }
finally { await rm(root, { recursive: true, force: true }); }
