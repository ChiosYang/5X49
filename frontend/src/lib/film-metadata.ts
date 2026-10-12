export const metadataFields = ["title", "original_title", "year", "overview"] as const;
export type MetadataField = typeof metadataFields[number];
export type MetadataValue = string | number | null;
export interface MetadataView {
  film_id: string;
  revision: string;
  fields: Record<MetadataField, {
    value: MetadataValue; manual: boolean; automatic_value: MetadataValue;
    automatic_source: { source_kind: string | null; conflicted: boolean };
  }>;
}
export type MetadataChange = { action: "set"; value: MetadataValue } | { action: "reset" };
export interface MetadataRequest {
  revision: string; idempotency_key: string; changes: Partial<Record<MetadataField, MetadataChange>>;
}
export function metadataRequestKey(random: Pick<Crypto, "getRandomValues"> = crypto) {
  return Array.from(random.getRandomValues(new Uint8Array(16)), value => value.toString(16).padStart(2, "0")).join("");
}
export function isMetadataReadCache(key: string) {
  return /^\/api\/films\/[^/]+\/(graph|metadata)$/.test(key)
    || key === "/api/library/missing" || key === "/api/explore" || key.startsWith("/api/explore/");
}
export function metadataDraft(view: MetadataView) {
  return Object.fromEntries(metadataFields.map(key => [key, String(view.fields[key].value ?? "")])) as Record<MetadataField, string>;
}
export function metadataModes(view: MetadataView) {
  return Object.fromEntries(metadataFields.map(key => [key, view.fields[key].manual])) as Record<MetadataField, boolean>;
}
export function metadataChanges(view: MetadataView, draft: Record<MetadataField, string>, manual: Record<MetadataField, boolean>) {
  const changes: MetadataRequest["changes"] = {};
  for (const key of metadataFields) {
    if (!manual[key]) {
      if (view.fields[key].manual) changes[key] = { action: "reset" };
      continue;
    }
    const text = draft[key].trim();
    if (key === "year" && text && (!/^\d{4}$/.test(text) || Number(text) < 1870 || Number(text) > 2100)) throw Error("year");
    if (key === "title" && !text) throw Error("title");
    if (Array.from(text).length > (key === "overview" ? 10000 : 300)) throw Error(key);
    const value = text ? (key === "year" ? Number(text) : text) : null;
    if (!view.fields[key].manual || value !== view.fields[key].value) changes[key] = { action: "set", value };
  }
  return changes;
}
