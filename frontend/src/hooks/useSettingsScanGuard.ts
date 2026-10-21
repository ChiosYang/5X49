"use client";

import { useSyncExternalStore } from "react";
import { settingsScanBlocked, subscribeSettingsScanGuard } from "@/lib/settings-scan-guard";

export function useSettingsScanGuard() {
  return useSyncExternalStore(subscribeSettingsScanGuard, settingsScanBlocked, () => false);
}
