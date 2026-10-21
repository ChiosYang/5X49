export interface AutosaveState<T, N> { draft: T | null; saving: boolean; notice: N | "saved" | null }
interface CompletedDraft<T> { version: number; value: T }

// Only an explicit completion event queues a write. Further typing invalidates that queue.
export function createCompletedInputAutosave<T, N extends string>(options: {
  initial: T | null;
  validate: (value: T) => { value: T; error: N | null };
  write: (value: T) => Promise<T>;
  failure: (failure: unknown, stale: boolean) => N;
  changed: (state: AutosaveState<T, N>) => void;
}) {
  let draft: T | null = null, confirmed = structuredClone(options.initial), latestSaved = structuredClone(options.initial);
  let version = 0, saving = false, notice: N | "saved" | null = null;
  let queued: CompletedDraft<T> | null = null, current: CompletedDraft<T> | null = null;
  let flight: Promise<void> | null = null;
  const clone = (value: T) => structuredClone(value);
  const emit = () => options.changed({ draft: draft === null ? null : clone(draft), saving, notice });
  const same = (left: T, right: T | null) => right !== null && JSON.stringify(left) === JSON.stringify(right);
  const edit = (value: T) => {
    if (draft === null && !saving) confirmed = structuredClone(latestSaved);
    draft = clone(value); version += 1; queued = null; notice = null; emit();
  };
  async function drain(first: CompletedDraft<T>) {
    saving = true; emit();
    let next: CompletedDraft<T> | null = first;
    try {
      while (next) {
        current = next; queued = null;
        try { confirmed = clone(await options.write(clone(current.value))); latestSaved = clone(confirmed); }
        catch (failure) { notice = options.failure(failure, current.version !== version); queued = null; break; }
        if (current.version === version) { draft = null; notice = "saved"; }
        const completed = queued as CompletedDraft<T> | null;
        next = completed?.version === version ? completed : null;
        if (next && same(next.value, confirmed)) { draft = null; notice = "saved"; next = null; }
      }
    } finally { current = null; queued = null; saving = false; flight = null; emit(); }
  }
  const commit = (): Promise<void> => {
    if (draft === null) return flight ?? Promise.resolve();
    const validated = options.validate(clone(draft));
    if (validated.error) { notice = validated.error; emit(); return flight ?? Promise.resolve(); }
    if (saving) {
      if (current?.version !== version) queued = { version, value: validated.value };
      return flight ?? Promise.resolve();
    }
    if (same(validated.value, confirmed)) { draft = null; notice = null; emit(); return Promise.resolve(); }
    flight = drain({ version, value: validated.value });
    return flight;
  };
  const discard = () => {
    if (saving) return;
    version += 1; draft = null; queued = null; confirmed = structuredClone(latestSaved); notice = null; emit();
  };
  const syncSaved = (value: T) => { latestSaved = clone(value); if (draft === null && !saving) confirmed = clone(value); };
  return { edit, commit, discard, syncSaved };
}

type RootsError = "saveFailed" | "absolute" | "overlap" | "incomplete";
export type RootsNotice = RootsError | "saved" | null;
export type RootsSaveState = AutosaveState<string[], RootsError>;

export function validateRootDraft(values: string[]) {
  const paths = values.map(value => value.trim());
  if (paths.some(value => !value)) return { paths, error: "incomplete" as const };
  const invalid = paths.some(value => /[\0\r\n]/.test(value)
    || (value.startsWith("\\\\") ? !/^\\\\[^\\/]+[\\/][^\\/]+/.test(value)
      : !value.startsWith("/") && !/^[a-z]:[\\/]/i.test(value) && !/^~[\\/].+/.test(value)));
  return { paths, error: invalid ? "absolute" as const : null };
}

export function createMediaRootsAutosave(options: {
  initial: string[] | null;
  write: (paths: string[]) => Promise<string[]>;
  changed: (state: RootsSaveState) => void;
}) {
  return createCompletedInputAutosave<string[], RootsError>({ ...options,
    validate: values => { const result = validateRootDraft(values); return { value: result.paths, error: result.error }; },
    failure: (failure, stale) => {
      const code = failure instanceof Error ? failure.message : "saveFailed";
      return !stale && (code === "absolute" || code === "overlap") ? code : "saveFailed";
    },
  });
}

type BaseUrlError = "invalidBaseUrl" | "baseUrlSaveFailed";
export type BaseUrlSaveState = AutosaveState<string, BaseUrlError>;
export function validateBaseUrl(raw: string) {
  const value = raw.trim();
  try {
    const url = new URL(value);
    return { value, error: (url.protocol === "http:" || url.protocol === "https:") && Boolean(url.hostname) ? null : "invalidBaseUrl" as const };
  } catch { return { value, error: "invalidBaseUrl" as const }; }
}
export function createBaseUrlAutosave(options: {
  initial: string | null;
  write: (value: string) => Promise<string>;
  changed: (state: BaseUrlSaveState) => void;
}) {
  return createCompletedInputAutosave<string, BaseUrlError>({ ...options, validate: validateBaseUrl, failure: () => "baseUrlSaveFailed" });
}
