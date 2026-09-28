export function normalizeLibrarySearch(value?: string | string[]) {
  return (Array.isArray(value) ? value[0] : value)?.trim().slice(0, 200) ?? "";
}
