import { getTranslations } from "next-intl/server";
import WatchHistoryClient from "./WatchHistoryClient";

export default async function WatchHistoryPage() {
  const t = await getTranslations("WatchHistory");

  return (
    <div className="min-h-screen bg-canvas px-5 py-6 text-ink selection:bg-inverse selection:text-inverse-ink sm:px-8 md:px-12 md:py-12">
      <div className="w-full space-y-14 pt-32">
        <header className="border-b border-line pb-8">
          <h1 className="type-display-editorial">{t("title")}</h1>
          <p className="mt-4 max-w-2xl text-sm font-bold uppercase tracking-widest text-ink-subtle">
            {t("subtitle")}
          </p>
        </header>
        <WatchHistoryClient />
      </div>
    </div>
  );
}
