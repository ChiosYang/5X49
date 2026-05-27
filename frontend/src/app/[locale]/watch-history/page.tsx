import { getTranslations } from "next-intl/server";
import WatchHistoryClient from "./WatchHistoryClient";

export default async function WatchHistoryPage() {
  const t = await getTranslations("WatchHistory");

  return (
    <div className="min-h-screen bg-black px-8 py-6 text-white selection:bg-white selection:text-black md:px-12 md:py-12">
      <div className="w-full space-y-14 pt-32">
        <header className="border-b border-neutral-900 pb-8">
          <h1 className="text-6xl font-serif tracking-tighter md:text-9xl">{t("title")}</h1>
          <p className="mt-4 max-w-2xl text-sm font-bold uppercase tracking-widest text-neutral-500">
            {t("subtitle")}
          </p>
        </header>
        <WatchHistoryClient />
      </div>
    </div>
  );
}
