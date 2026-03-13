'use client'

import { useEffect, useState } from 'react'
import { useBismuthSocket } from '@/hooks/useBismuthSocket'
import SetupView from '@/components/SetupView'
import ProjectSetupView from '@/components/ProjectSetupView'
import ProjectsScreen from '@/components/ProjectsScreen'
import SettingsScreen from '@/components/SettingsScreen'
import DashboardView from '@/components/DashboardView'

type View = 'loading' | 'setup' | 'projects' | 'new-project' | 'settings' | 'dashboard'

export default function Home() {
  const { state, connected, agentUrl, loadProject } = useBismuthSocket()
  const [view, setView] = useState<View>('loading')

  // Initial routing — only fires while view is still 'loading'
  useEffect(() => {
    if (!connected || !state || view !== 'loading') return

    if (!state.initialised) {
      setView('setup')
    } else if (state.project && state.phase !== 'setup') {
      setView('dashboard')
    } else {
      setView('projects')
    }
  }, [state, connected, view])

  if (view === 'loading') return (
    <div className="h-screen flex items-center justify-center bg-bismuth-bg">
      <div className="text-center">
        <div className="text-bismuth-accent text-2xl font-mono mb-3 animate-pulse-glow">BISMUTH</div>
        <div className="text-bismuth-dim text-sm">Connecting to agent...</div>
      </div>
    </div>
  )

  if (view === 'setup')    return <SetupView agentUrl={agentUrl!} />
  if (view === 'settings') return <SettingsScreen agentUrl={agentUrl!} onBack={() => setView('projects')} />

  if (view === 'new-project') return (
    <ProjectSetupView
      agentUrl={agentUrl!}
      onBack={() => setView('projects')}
    />
  )

  if (view === 'projects') return (
    <ProjectsScreen
      agentUrl={agentUrl!}
      onNewProject={() => setView('new-project')}
      onOpenProject={async (id) => {
        await loadProject(id)
        setView('dashboard')
      }}
      onOpenSettings={() => setView('settings')}
    />
  )

  return <DashboardView onGoToProjects={() => setView('projects')} />
}
