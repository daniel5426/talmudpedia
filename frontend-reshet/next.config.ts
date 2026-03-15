import type { NextConfig } from "next";

const localBackendTarget =
  process.env.NEXT_PUBLIC_BACKEND_URL?.trim() || "http://127.0.0.1:8026";

const nextConfig: NextConfig = {
  rewrites: async () => {
    return [
      {
        source: "/api/py/:path*",
        destination:
          process.env.NODE_ENV === "development"
            ? `${localBackendTarget}/:path*`
            : "/api/py/:path*",
      },
    ];
  },
};

export default nextConfig;
