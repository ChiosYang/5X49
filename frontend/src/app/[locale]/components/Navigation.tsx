import { Search } from "lucide-react";
import { Link } from "@/i18n/routing";
import WorkflowRuntimeStatus from "@/components/WorkflowRuntimeStatus";
import NavigationMenu from "./NavigationMenu";

export default function Navigation() {
  return (
    <nav className="z-navigation fixed top-0 right-0 left-0 flex items-center justify-between p-8 text-ink">
      {/* Left: Menu Trigger */}
      <NavigationMenu />

      {/* Center: Logo */}
      <Link href="/" className="focus-ring z-navigation absolute left-1/2 -translate-x-1/2 font-serif text-2xl font-bold tracking-tighter drop-shadow-lg">
        5X49
      </Link>

      {/* Right: Search and background jobs */}
      <div className="flex items-center gap-4">
        <Search className="w-5 h-5 opacity-0 md:opacity-100 drop-shadow-lg" /> {/* Hidden on mobile or visual only */}
        <WorkflowRuntimeStatus />
      </div>
    </nav>
  );
}
