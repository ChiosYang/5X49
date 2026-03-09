import type { NextConfig } from "next";
import createNextIntlPlugin from 'next-intl/plugin';

const withNextIntl = createNextIntlPlugin();

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `http://backend:8000/:path*`, // Proxy to Backend
      },
      {
        source: "/media/:path*",
        destination: `http://backend:8000/media/:path*`, // Proxy media to Backend
      }
    ];
  },
};

export default withNextIntl(nextConfig);
