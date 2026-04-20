/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  images: {
    remotePatterns: [
      { protocol: "https", hostname: "**.craigslist.org" },
      { protocol: "https", hostname: "**.ebayimg.com" },
      { protocol: "https", hostname: "images.craigslist.org" },
    ],
  },
};

module.exports = nextConfig;
