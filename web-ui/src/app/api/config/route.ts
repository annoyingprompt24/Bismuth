import { NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'

export async function GET() {
  // These are read server-side at runtime — not baked in at build time
  // This means changing AGENT_EXTERNAL_URL in docker-compose never requires a rebuild
  return NextResponse.json({
    agentUrl: process.env.AGENT_EXTERNAL_URL || 'http://localhost:3068',
    giteaUrl: process.env.GITEA_EXTERNAL_URL || 'http://localhost:3001',
  })
}