export type HealthState = "unchecked" | "queued" | "checking" | "passed" | "abnormal" | "incomplete" | "unsupported";
export type HealthConfig = { enabled: boolean; paused: boolean; start_minute: number; end_minute: number; daily_budget_minutes: number };
export type HealthFile = {
  id: string | null; asset_id: string; film_id: string | null; library_item_id: string | null;
  title: string | null; filename: string | null; status: HealthState; container_status: HealthState; decode_status: HealthState;
  current: boolean; version_key: string | null; version: { size?: number; mtime_ns?: number } | null;
  decoded_seconds: number; duration_seconds: number | null; checked_at: number | null;
  error_code: string | null; error_summary: string | null; unread?: boolean; unavailable_reason?: string | null;
};
export type HealthStatus = {
  config: HealthConfig; reason: string; counts: Record<HealthState, number>; total: number; unread: number;
  active_id: string | null; schedule_timezone: string; used_seconds: number; budget_day: string;
  load: { observable: boolean; cpu: number | null; disk: number | null }; queue_sweep_pending: boolean;
  active_progress: { decoded_seconds: number; duration_seconds: number | null } | null;
};
export const healthStates: HealthState[] = ["unchecked", "queued", "checking", "passed", "abnormal", "incomplete", "unsupported"];
export function parseHealthLocation(search: URLSearchParams) {
  const rawFilter = search.get("health_state") ?? "abnormal";
  const filter = ["all", ...healthStates].includes(rawFilter) ? rawFilter : "abnormal";
  const rawOffset = search.get("health_offset") ?? "0";
  const offset = /^\d+$/.test(rawOffset) && Number.isSafeInteger(Number(rawOffset)) ? Math.min(1_000_000, Number(rawOffset)) : 0;
  const rawSelected = search.get("health_file");
  const selected = rawSelected && /^[a-z0-9_-]{1,100}$/i.test(rawSelected) ? rawSelected : null;
  return { filter, offset, selected };
}
export function videoHealthHref(search: string, location: ReturnType<typeof parseHealthLocation>) {
  const params = new URLSearchParams(search);
  params.set("section", "video-checks");
  params.set("health_state", location.filter);
  params.set("health_offset", String(location.offset));
  if (location.selected) params.set("health_file", location.selected); else params.delete("health_file");
  return `/settings?${params.toString()}#video-health`;
}
export function minuteTime(minute: number): string {
  return `${String(Math.floor(minute / 60)).padStart(2, "0")}:${String(minute % 60).padStart(2, "0")}`;
}
export function parseTime(value: string): number | null {
  if (!/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(value)) return null;
  const [hour, minute] = value.split(":").map(Number);
  return hour * 60 + minute;
}
