/** @type {import('next').NextConfig} */
// Standalone output is only for the Docker image; ./start.sh uses `next start`.
const nextConfig = process.env.NEXT_STANDALONE ? { output: "standalone" } : {};
export default nextConfig;
