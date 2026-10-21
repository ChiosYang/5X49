import type { AutosaveState } from "./settings-autosave";

interface Controller<T> {
  edit: (value: T) => void;
  commit: () => Promise<void>;
  discard: () => void;
  syncSaved: (value: T) => void;
  baseline: () => T | null;
}
interface SessionOptions<T, N extends string, R> {
  initial: R | null;
  value: (result: R) => T;
  write: (value: T) => Promise<R>;
  create: (options: { initial: T | null; write: (value: T) => Promise<T>; changed: (state: AutosaveState<T, N>) => void }) => Controller<T>;
  active?: (active: boolean) => void;
  changed?: (state: AutosaveState<T, N>) => void;
  retainFailedDraft?: boolean;
}

// One bounded session per setting in this browser runtime. A component remount
// reconnects to the same revision/queue instead of creating a competing writer.
export function createAutosaveSessionRegistry<T, N extends string, R>() {
  function create(options: SessionOptions<T, N, R>) {
    let result = options.initial;
    let state: AutosaveState<T, N> = { draft: null, saving: false, notice: null };
    let snapshot = { ...state, result };
    const listeners = new Set<() => void>();
    const emit = () => { snapshot = { ...state, result }; for (const listener of listeners) listener(); };
    const controller = options.create({
      initial: result === null ? null : options.value(result),
      write: async value => { result = await options.write(value); return options.value(result); },
      changed: next => { state = next; options.changed?.(next); emit(); },
    });
    return {
      edit: controller.edit, commit: controller.commit, discard: controller.discard, baseline: controller.baseline,
      getSnapshot: () => snapshot,
      syncSaved: (saved: R) => {
        // A pending response/draft owns its displayed value. SWR's older read
        // must not replace it while a write is being handed between mounts.
        if (state.saving || state.draft !== null) return;
        controller.syncSaved(options.value(saved));
        if (result !== saved) { result = saved; emit(); }
      },
      subscribe: (listener: () => void) => {
        listeners.add(listener); options.active?.(true); options.changed?.(state);
        return () => {
          listeners.delete(listener);
          if (listeners.size) return;
          options.active?.(false);
          // React StrictMode can detach and reattach in the same turn.
          queueMicrotask(() => {
            const keepFailure = options.retainFailedDraft && state.notice !== null && state.notice !== "saved";
            if (!listeners.size && !state.saving && !keepFailure) controller.discard();
          });
        };
      },
    };
  }
  let session: ReturnType<typeof create> | null = null;
  return { get: (options: () => SessionOptions<T, N, R>, reuse = true) => {
    if (!reuse) return create(options()); // Do not retain request state during SSR.
    return session ??= create(options());
  } };
}
