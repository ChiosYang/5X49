import VideoHealthNotice from "@/components/VideoHealthNotice";
import { Search } from "lucide-react";
import { Link } from "@/i18n/routing";
import WorkflowRuntimeStatus from "@/components/WorkflowRuntimeStatus";
import NavigationMenu from "./NavigationMenu";
import { getTranslations } from "next-intl/server";

export default async function Navigation() {
  const t = await getTranslations("Navigation");
  return (
    <nav className="z-navigation fixed top-0 right-0 left-0 flex items-center justify-between p-8 pr-0 text-ink sm:pr-8">
      {/* Left: Menu Trigger */}
      <NavigationMenu />

      {/* Center: Logo */}
      <Link href="/" className="focus-ring z-navigation absolute left-1/2 -translate-x-1/2 font-serif text-2xl font-bold tracking-tighter drop-shadow-lg">
        5X49
      </Link>

      {/* Right: Search and background jobs */}
      <div className="flex items-center gap-0 sm:gap-4">
        <Link href="/search" aria-label={t("search")} className="focus-ring inline-flex h-11 w-11 items-center justify-center">
          <Search className="h-5 w-5 drop-shadow-lg" aria-hidden="true" />
        </Link>
        <VideoHealthNotice />
        <WorkflowRuntimeStatus />
      </div>
    </nav>
  );
}
