import { defineRouting } from 'next-intl/routing';

export const routing = defineRouting({
    locales: ['en', 'zh'],
    defaultLocale: 'zh',
    localePrefix: 'as-needed'
});

// Lightweight wrappers around Next.js' navigation APIs
// that will consider the routing configuration
import { createNavigation } from 'next-intl/navigation';
export const { Link, redirect, usePathname, useRouter, getPathname } = createNavigation(routing);
