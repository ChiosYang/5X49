import { Search } from "lucide-react";
import { Link } from "@/i18n/routing";
import JobRuntimeStatus from "@/components/JobRuntimeStatus";
import NavigationMenu from "./NavigationMenu";

export default function Navigation() {
  return (
    <nav className="fixed top-0 left-0 right-0 z-[60] flex justify-between items-center p-8 text-white">
      {/* Left: Menu Trigger */}
      <NavigationMenu />

      {/* Center: Logo */}
      <Link href="/" className="font-serif font-bold text-2xl tracking-tighter absolute left-1/2 -translate-x-1/2 z-50 drop-shadow-lg">
        5X49
      </Link>

      {/* Right: Search and background jobs */}
      <div className="flex items-center gap-4">
        <Search className="w-5 h-5 opacity-0 md:opacity-100 drop-shadow-lg" /> {/* Hidden on mobile or visual only */}
        <JobRuntimeStatus />
      </div>
    </nav>
  );
}
