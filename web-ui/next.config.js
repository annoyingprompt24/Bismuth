/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  typescript: {
    ignoreBuildErrors: true,
  },
  eslint: {
    ignoreDuringBuilds: true,
  },
  env: {
    AGENT_API_URL: process.env.AGENT_API_URL || 'http://localhost:5000',
    GITEA_URL: process.env.GITEA_URL || 'http://localhost:3001',
  },
}

module.exports = nextConfig
