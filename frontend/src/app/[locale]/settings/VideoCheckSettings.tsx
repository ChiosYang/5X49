"use client";

import VideoHealthSettings from "@/components/settings/VideoHealthSettings";
import VideoHealthMaintenance from "@/components/VideoHealthMaintenance";

export default function VideoCheckSettings() {
  return <div className="space-y-8"><VideoHealthSettings mode="controls" /><VideoHealthMaintenance /></div>;
}
