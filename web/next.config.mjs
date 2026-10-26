/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // `next dev` blocks its client resources for origins it does not know, which leaves
  // pages unhydrated (stuck on "Loading…") when opened as 127.0.0.1 or by public IP.
  // Extra hosts (e.g. an EC2 public IP) come from SPLM_ALLOWED_DEV_ORIGINS, comma-separated.
  allowedDevOrigins: [
    "127.0.0.1",
    "localhost",
    ...(process.env.SPLM_ALLOWED_DEV_ORIGINS ?? "").split(",").map((h) => h.trim()).filter(Boolean),
  ],
  // The Python API runs separately. Proxying it under /api keeps the browser on one
  // origin, so no CORS preflight in development and no origin config in production.
  // In ACM mode (NEXT_PUBLIC_APP_MODE=acm, set by ACM's ./start.sh) the home page is the
  // ACM demo; the MLM Playground stays available at /mlm.
  async redirects() {
    return process.env.NEXT_PUBLIC_APP_MODE === "acm"
      ? [{ source: "/", destination: "/acm", permanent: false }]
      : [];
  },
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
