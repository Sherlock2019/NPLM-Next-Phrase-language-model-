/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // The Python API runs separately. Proxying it under /api keeps the browser on one
  // origin, so no CORS preflight in development and no origin config in production.
  async rewrites() {
    const target = process.env.SPLM_API_URL ?? "http://127.0.0.1:8001";
    return [
      {
        source: "/api/:path*",
        destination: `${target}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
