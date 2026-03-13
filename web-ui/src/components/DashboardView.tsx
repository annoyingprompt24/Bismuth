'use client'

import { useBismuthSocket } from '@/hooks/useBismuthSocket'
import StatusBar from './StatusBar'
import RoadmapTimeline from './RoadmapTimeline'
import Terminal from './Terminal'

export default function DashboardView() {
  const socket = useBismuthSocket()

  return (
    <div className="h-screen flex flex-col bg-bismuth-bg overflow-hidden">
      {/* Top status bar */}
      <StatusBar state={socket.state} connected={socket.connected} agentUrl={socket.agentUrl} />

      {/* Main split layout */}
      <div className="flex flex-1 overflow-hidden">

        {/* Left — Roadmap timeline */}
        <div className="w-96 flex-shrink-0 border-r border-bismuth-border overflow-y-auto">
          <RoadmapTimeline
            roadmap={socket.roadmap}
            state={socket.state}
            agentUrl={socket.agentUrl}
            onAcceptRoadmap={socket.acceptRoadmap}
            onAcceptSprints={socket.acceptSprints}
            onResume={socket.sendResume}
          />
        </div>

        {/* Right — Terminal / chat */}
        <div className="flex-1 flex flex-col overflow-hidden">
          <Terminal
            messages={socket.messages}
            logs={socket.logs}
            state={socket.state}
            onSend={socket.sendMessage}
            onBreak={socket.sendBreak}
            onResume={socket.sendResume}
          />
        </div>
      </div>
    </div>
  )
}
