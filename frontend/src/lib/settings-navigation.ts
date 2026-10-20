export const settingSections = [
  "general", "library", "connections", "library-maintenance",
  "video-checks", "diagnostics", "backup", "cleanup",
] as const;

export type SettingSection = (typeof settingSections)[number];

export function settingsHref(section: SettingSection, anchor = "") {
  return `/settings?section=${section}${anchor ? `#${anchor.replace(/^#/, "")}` : ""}`;
}

export function resolveSettingsLocation(value: string | null, hash = "") {
  let section: SettingSection = settingSections.includes(value as SettingSection)
    ? value as SettingSection
    : value === "integrations" ? "connections" : value === "maintenance" ? "diagnostics" : "general";
  let anchor = hash.replace(/^#/, "");
  if (["danger-zone", "clear-data"].includes(anchor)) {
    section = "cleanup"; anchor = "danger-zone";
  } else if (["backup", "backup-heading", "backup-download", "restore", "restore-title"].includes(anchor)) {
    section = "backup";
    anchor = anchor.startsWith("restore") ? "restore" : "backup-download";
  } else if (["video-health", "video-health-maintenance", "video-health-controls"].includes(anchor)) {
    section = "video-checks";
  } else if (anchor === "video-health-settings") {
    section = "library";
  } else if (["library-system-status", "system-status", "runtime"].includes(anchor)) {
    section = "diagnostics"; anchor = "runtime";
  }
  return { section, anchor };
}

export function canonicalSettingsHref(search: string, hash = "") {
  const params = new URLSearchParams(search);
  const { section, anchor } = resolveSettingsLocation(params.get("section"), hash);
  params.set("section", section);
  return `/settings?${params.toString()}${anchor ? `#${anchor}` : ""}`;
}

export function legacySettingsHref(source: "manage" | "health", hash = "", search = "") {
  const anchor = hash.replace(/^#/, "");
  if (source === "manage" && anchor === "metadata-reviews") return "/library?view=metadata";
  if (source === "manage" && anchor === "root-video-reviews") return "/library?view=inbox";
  const params = new URLSearchParams(search);
  params.set("section", source === "manage" ? "library-maintenance" : "diagnostics");
  if (["watcher", "organizer"].includes(anchor)) { params.set("section", "diagnostics"); return canonicalSettingsHref(params.toString(), "#runtime"); }
  return canonicalSettingsHref(params.toString(), anchor === "sync" ? "#scan" : hash);
}
