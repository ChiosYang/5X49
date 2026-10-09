import { getTranslations } from "next-intl/server";
import MaintenanceSettings from "../../settings/MaintenanceSettings";

export default async function AdminHealthPage() {
  const t = await getTranslations("Maintenance");
  return <main className="page-x min-h-screen bg-canvas pt-32 pb-16 text-ink">
    <h1 className="type-display-ui mb-10">{t("title")}</h1>
    <div className="max-w-3xl"><MaintenanceSettings /></div>
  </main>;
}
