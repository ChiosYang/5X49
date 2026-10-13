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
    const response = intlProxy(request);
    if (request.headers.get('next-router-prefetch') === '1') {
        // Prefetching an old-language link must not change the user's language.
        const cookies = response.headers.getSetCookie().filter(cookie => !cookie.startsWith('NEXT_LOCALE='));
        response.headers.delete('set-cookie');
        response.headers.delete('x-middleware-set-cookie');
        cookies.forEach(cookie => response.headers.append('set-cookie', cookie));
        if (cookies.length) response.headers.set('x-middleware-set-cookie', cookies.join(','));
    }
    return response;
}

export const config = {
    // Match only internationalized pathnames
    matcher: ['/', '/(zh|en)/:path*', '/((?!api|media|_next|_vercel|.*\\..*).*)']
};
