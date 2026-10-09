/** A committed write stays successful even when subsequent reads fail. */
export async function commitViewingWrite<T>(
  write: () => Promise<T>,
  committed: (value: T) => void,
  refresh: () => Promise<unknown>,
): Promise<{ value: T; refreshFailed: boolean }> {
  const value = await write();
  committed(value);
  try {
    await refresh();
    return { value, refreshFailed: false };
  } catch {
    return { value, refreshFailed: true };
  }
}

/** Revalidate reads explicitly: SWR's implicit revalidation swallows fetch errors. */
export async function refreshViewingReadCaches(
  keys: string[],
  read: (key: string) => Promise<unknown>,
  publish: (key: string, read: Promise<unknown>) => Promise<unknown>,
): Promise<void> {
  const outcomes = await Promise.allSettled(keys.map((key) => publish(key, read(key))));
  const failure = outcomes.find((outcome) => outcome.status === "rejected");
  if (failure?.status === "rejected") throw failure.reason;
}

export function actionFailureKind(error: unknown): "connection" | "unavailable" | "conflict" | "rejected" {
  if (error instanceof TypeError) return "connection";
  if (error instanceof Error && "status" in error && typeof error.status === "number") {
    if (error.status >= 500) return "unavailable";
    if (error.status === 409) return "conflict";
  }
  return "rejected";
}

/** Never replay a committed action to recover failed reads. */
export async function executeFilmAction<T>(
  write: () => Promise<T>, committed: (value: T) => void, refresh: () => Promise<unknown>,
) {
  try {
    const result = await commitViewingWrite(write, committed, refresh);
    return { status: result.refreshFailed ? "refreshFailed" as const : "saved" as const, value: result.value };
  } catch (error) {
    return { status: "failed" as const, reason: actionFailureKind(error) };
  }
}
