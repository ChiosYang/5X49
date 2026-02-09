"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Search, Menu, X } from "lucide-react";
import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";

export default function Navigation() {
  const [isOpen, setIsOpen] = useState(false);
  const pathname = usePathname();

  const toggleMenu = () => setIsOpen(!isOpen);

  // Close menu when route changes
  if (isOpen && typeof window !== "undefined") {
    // Optional: lock body scroll? A24 does.
  }

  return (
    <>
      <nav className="fixed top-0 left-0 right-0 z-[60] flex justify-between items-center p-8 text-white mix-blend-exclusion">
        {/* Left: Menu Trigger */}
        <button 
          onClick={toggleMenu}
          className="flex items-center gap-2 uppercase text-sm font-bold tracking-widest hover:opacity-70 transition-opacity"
        >
          {isOpen ? (
            <>
              <X className="w-5 h-5" /> CLOSE
            </>
          ) : (
            <>
              <Menu className="w-5 h-5" /> MENU
            </>
          )}
        </button>

        {/* Center: Logo */}
        <Link href="/" className="font-serif font-bold text-2xl tracking-tighter absolute left-1/2 -translate-x-1/2 z-50">
          A24.ARCHIVE
        </Link>

        {/* Right: Search Icon (Optional specifically requested in sidebar, but nice to adhere to A24 pattern where search is accessible) */}
        <div className="flex gap-6">
           <Search className="w-5 h-5 opacity-0 md:opacity-100" /> {/* Hidden on mobile or visual only */}
        </div>
      </nav>

      {/* Sidebar Overlay */}
      <AnimatePresence>
        {isOpen && (
          <>
            {/* Backdrop */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={toggleMenu}
              className="fixed inset-0 bg-black/50 z-40 backdrop-blur-sm"
            />
            
            {/* Sidebar */}
            <motion.div
              initial={{ x: "-100%" }}
              animate={{ x: 0 }}
              exit={{ x: "-100%" }}
              transition={{ type: "tween", duration: 0.4, ease: [0.16, 1, 0.3, 1] }} 
              className="fixed top-0 left-0 bottom-0 w-full md:w-[40vw] bg-black z-50 p-8 md:p-16 flex flex-col justify-center shadow-2xl border-r border-neutral-900"
            >
              <div className="space-y-4 md:space-y-6">
                <Link 
                  href="/library" 
                  onClick={toggleMenu}
                  className="block text-5xl md:text-7xl font-bold tracking-tighter text-white hover:text-neutral-400 transition-colors"
                >
                  Films
                </Link>
                <Link 
                  href="/" 
                  onClick={toggleMenu}
                  className="block text-5xl md:text-7xl font-bold tracking-tighter text-white hover:text-neutral-400 transition-colors"
                >
                  Search
                </Link>
                <Link 
                  href="#" 
                  className="block text-5xl md:text-7xl font-bold tracking-tighter text-neutral-600 hover:text-neutral-500 transition-colors cursor-not-allowed"
                >
                  Television
                </Link>
                <Link 
                  href="#" 
                  className="block text-5xl md:text-7xl font-bold tracking-tighter text-neutral-600 hover:text-neutral-500 transition-colors cursor-not-allowed"
                >
                  Notes
                </Link>
              </div>

              {/* Footer in Sidebar */}
              <div className="absolute bottom-16 left-8 md:left-16 text-neutral-500 text-xs font-bold uppercase tracking-widest space-y-2">
                <p>Film Genealogy Project</p>
                <p>Based on A24 Design System</p>
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </>
  );
}
