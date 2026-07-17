import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  images: {
    // Clerk serves user avatars from this host. Next.js 16 requires external
    // image hosts to be allow-listed via `remotePatterns` (`domains` is deprecated).
    remotePatterns: [{ protocol: "https", hostname: "img.clerk.com" }],
  },
};

export default nextConfig;
