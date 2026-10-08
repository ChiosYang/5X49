import { spawn } from 'node:child_process';
import { createWriteStream } from 'node:fs';
import path from 'node:path';

export function managedProcesses(env, output) {
  const children = new Set();
  const states = new WeakMap();
  function start(command, args, cwd, log) {
    const stream = log ? createWriteStream(path.join(output, log), { flags: 'a' }) : null;
    const child = spawn(command, args, { cwd, env, stdio: stream ? ['ignore', 'pipe', 'pipe'] : 'inherit' });
    children.add(child);
    if (stream) { child.stdout.pipe(stream); child.stderr.pipe(stream); }
    const state = { error: null, ended: false, done: null };
    state.done = new Promise(resolve => {
      const complete = () => { if (state.ended) return; state.ended = true; children.delete(child); stream?.end(); resolve(); };
      child.once('error', error => { state.error = error; complete(); });
      child.once('exit', complete);
    });
    stream?.once('error', error => { state.error = error; child.kill('SIGTERM'); });
    states.set(child, state);
    return child;
  }
  async function finish(child) {
    const state = states.get(child); await state.done;
    if (state.error) throw state.error;
    if (child.exitCode !== 0) throw Error(`Process exited ${child.exitCode ?? child.signalCode}`);
  }
  async function stop(child) {
    if (!child || states.get(child).ended) return;
    const exited = states.get(child).done;
    child.kill('SIGTERM');
    const timer = setTimeout(() => child.kill('SIGKILL'), 8000);
    await exited; clearTimeout(timer);
  }
  async function ready(url, child) {
    for (let i = 0; i < 120; i++) {
      if (states.get(child).ended) throw states.get(child).error || Error(`Server exited before ready: ${url}`);
      try { if ((await fetch(url, { signal: AbortSignal.timeout(1000) })).ok) return; } catch {}
      await new Promise(r => setTimeout(r, 250));
    }
    throw Error(`Server readiness timed out: ${url}`);
  }
  return { start, finish, stop, ready, children };
}
