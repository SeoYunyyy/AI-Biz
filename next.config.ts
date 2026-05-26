import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // jsdom / readability는 Node.js 전용 — 클라이언트 번들에서 제외
  serverExternalPackages: ['jsdom', '@mozilla/readability'],
  images: {
    remotePatterns: [
      { protocol: "https", hostname: "i.ytimg.com" },
      { protocol: "https", hostname: "img.youtube.com" },
      { protocol: "https", hostname: "**.tistory.com" },
      { protocol: "https", hostname: "**.medium.com" },
      { protocol: "https", hostname: "**.velog.io" },
      { protocol: "https", hostname: "**.brunch.co.kr" },
      { protocol: "https", hostname: "**.githubusercontent.com" },
      { protocol: "https", hostname: "**.unsplash.com" },
      { protocol: "http", hostname: "**" },
      { protocol: "https", hostname: "**" },
    ],
  },
};

export default nextConfig;
