"use client";

import { useEffect } from "react";
import { useTranslations } from "next-intl";
import { useRouter } from "@/i18n/routing";
import { legacySettingsHref } from "@/lib/settings-navigation";
import { StateMessage } from "@/components/ui/Feedback";

export default function LegacySettingsRedirect({ source }: { source: "manage" | "health" }) {
  const router = useRouter();
  const t = useTranslations("SettingsArea");
  useEffect(() => {
    router.replace(legacySettingsHref(source, window.location.hash, window.location.search));
  }, [router, source]);
  return <main className="page-x min-h-screen bg-canvas pt-32 text-ink"><StateMessage state="loading">{t("opening")}</StateMessage></main>;
}
