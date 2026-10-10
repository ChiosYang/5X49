import type { NextConfig } from "next";
import createNextIntlPlugin from 'next-intl/plugin';

const withNextIntl = createNextIntlPlugin();

const nextConfig: NextConfig = {
  output: "standalone",
  // next-intl must rewrite against the public request host. Normalizing
  // 127.0.0.1 to localhost makes Next treat the locale rewrite as external,
  // re-enter the proxy, and redirect the default locale back to itself.
  skipProxyUrlNormalize: true,
  images: {
    localPatterns: [
      {
        pathname: "/api/media/**",
      },
      {
        pathname: "/api/artwork-cache/**",
      },
    ],
    remotePatterns: [
      {
        protocol: "https",
        hostname: "image.tmdb.org",
        pathname: "/t/p/**",
      },
    ],
  },
};

export default withNextIntl(nextConfig);
