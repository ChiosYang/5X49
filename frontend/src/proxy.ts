import createMiddleware from 'next-intl/middleware';
import type { NextRequest } from 'next/server';

const intlProxy = createMiddleware({
    // A list of all locales that are supported
    locales: ['en', 'zh'],

    // Used when no locale matches
    defaultLocale: 'zh',

    // Rely on the cookie NEXT_LOCALE first.
    // Using prefix="as-needed" means we won't inject /zh/ into the URL if it's the default,
    // or we can use "always" to be explicit.
    localePrefix: 'as-needed'
});

export function proxy(request: NextRequest) {
    return intlProxy(request);
}

export const config = {
    // Match only internationalized pathnames
    matcher: ['/', '/(zh|en)/:path*', '/((?!api|_next|_vercel|.*\\..*).*)']
};
