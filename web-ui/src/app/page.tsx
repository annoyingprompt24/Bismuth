'use client'

import { useEffect, useState } from 'react'
import { useBismuthSocket } from '@/hooks/useBismuthSocket'
import SetupView from '@/components/SetupView'
import ProjectSetupView from '@/components/ProjectSetupView'
import DashboardView from '@/components/DashboardView'

export default function Home() {
  const { state, connected } = useBismuthSocket()
  const [view, setView] = useState<'loading' | 'setup' | 'project' | 'dashboard'>('loading')

  useEffect(() => {
    if (!connected) return
    if (!state) return

    if (!state.initialised) {
      setView('setup')
    } else if (!state.project || state.phase === 'setup') {
      setView('project')
    } else {
      setView('dashboard')
    }
  }, [state, connected])

  if (view === 'loading') {
    return (
      <div className="h-screen flex items-center justify-center bg-bismuth-bg">
        <div className="text-center">
          <div className="text-bismuth-accent text-2xl font-mono mb-3 animate-pulse-glow">BISMUTH</div>
          <div className="text-bismuth-dim text-sm">Connecting to agent...</div>
        </div>
      </div>
    )
  }

  if (view === 'setup') return <SetupView />
  if (view === 'project') return <ProjectSetupView />
  return <DashboardView />
}
