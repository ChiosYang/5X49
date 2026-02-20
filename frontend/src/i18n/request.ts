import { getRequestConfig } from 'next-intl/server';

// Can be imported from a shared config
const locales = ['en', 'zh'];

export default getRequestConfig(async ({ requestLocale }) => {
    // This typically comes from the locale parameter in the URL segment
    // But here we might read it from a cookie in middleware, 
    // For the getRequestConfig, Next.js passes the resolved locale
    let locale = await requestLocale;

    if (!locale || !locales.includes(locale)) {
        locale = 'zh'; // Default fallback
    }

    return {
        locale,
        messages: (await import(`../../messages/${locale}.json`)).default
    };
});
