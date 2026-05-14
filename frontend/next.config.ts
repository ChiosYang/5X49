import type { NextConfig } from "next";
import createNextIntlPlugin from 'next-intl/plugin';

const withNextIntl = createNextIntlPlugin();

const backendUrl = process.env.NODE_ENV === 'development' 
  ? 'http://127.0.0.1:8000' 
  : (process.env.BACKEND_URL || 'http://backend:8000');

const nextConfig: NextConfig = {
  output: "standalone",
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
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/:path*`, // Proxy to Backend
      },
      {
        source: "/media/:path*",
        destination: `${backendUrl}/media/:path*`, // Proxy media to Backend
      }
    ];
  },
};

export default withNextIntl(nextConfig);
