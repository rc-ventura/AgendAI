/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  compress: false,
  experimental: {
    serverActions: {
      bodySizeLimit: "10mb",
    },
  },
};

export default nextConfig;
