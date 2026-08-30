import type { NextConfig } from 'next';

const basePath = process.env.PAGES_BASE_PATH ?? '';

const nextConfig: NextConfig = {
  output: process.env.STATIC_EXPORT === 'true' ? 'export' : undefined,
  basePath,
  assetPrefix: basePath || undefined,
  trailingSlash: true,
};

export default nextConfig;
