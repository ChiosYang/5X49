"use client";
import useSWR from "swr";
import { Bell } from "lucide-react";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/routing";
import { API } from "@/lib/api";
import type { HealthStatus } from "@/lib/video-health";

export default function VideoHealthNotice() {
  const t = useTranslations("VideoHealth");
  const { data } = useSWR<HealthStatus>(API.videoHealth(), { refreshInterval: 15000 });
  if (!data?.unread) return null;
  return <Link href="/library/manage#video-health" aria-label={t("notification", { count: data.unread })} className="focus-ring relative inline-flex h-11 w-11 items-center justify-center text-warning">
    <Bell className="h-5 w-5" aria-hidden="true" /><span aria-hidden="true" className="absolute top-0 right-0 text-[10px]">{data.unread > 99 ? "99+" : data.unread}</span>
  </Link>;
}
