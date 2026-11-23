import { getTranslations } from "next-intl/server";
import LibraryActivityClient from "./LibraryActivityClient";

export default async function LibraryActivityPage() {
  const t = await getTranslations("Activity");

  return (
    <div className="page-x min-h-screen bg-canvas py-6 text-ink selection:bg-inverse selection:text-inverse-ink md:py-12">
      <div className="w-full space-y-12 pt-32">
        <header>
          <h1 className="type-display-editorial">
            {t("title")}
          </h1>
        </header>
        <LibraryActivityClient />
      </div>
    </div>
  );
}
