'use client'

import { useState, useEffect } from 'react'

interface Project {
  id: string
  name: string
  status: string
  phase: string
  current_sprint: number
  total_sprints: number
  created_at: string | null
  completed_at: string | null
}

const STATUS_DOT: Record<string, string> = {
  grey:   'bg-bismuth-muted',
  green:  'bg-bismuth-green animate-pulse',
  yellow: 'bg-bismuth-yellow animate-pulse',
  red:    'bg-bismuth-red animate-pulse',
  blue:   'bg-bismuth-blue animate-pulse',
}

const PHASE_LABEL: Record<string, string> = {
  setup:                    'Setup',
  planning:                 'Generating Roadmap',
  awaiting_roadmap_approval:'Roadmap Review',
  awaiting_sprint_approval: 'Sprint Plan Review',
  running:                  'Running',
  paused:                   'Paused',
  complete:                 'Complete',
  error:                    'Error',
}

export default function ProjectsScreen({
  agentUrl,
  onNewProject,
  onOpenProject,
  onOpenSettings,
}: {
  agentUrl: string
  onNewProject: () => void
  onOpenProject: (id: string) => void
  onOpenSettings: () => void
}) {
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [loadingId, setLoadingId] = useState<string | null>(null)

  useEffect(() => {
    fetch(`${agentUrl}/projects`)
      .then(r => r.json())
      .then(data => { setProjects(data); setLoading(false) })
      .catch(() => setLoading(false))
  }, [agentUrl])

  const handleOpen = async (id: string) => {
    setLoadingId(id)
    try {
      await onOpenProject(id)
    } finally {
      setLoadingId(null)
    }
  }

  return (
    <div className="h-screen bg-bismuth-bg flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-8 py-5 border-b border-bismuth-border flex-shrink-0">
        <div>
          <div className="text-bismuth-accent font-mono font-medium tracking-widest text-sm">BISMUTH</div>
          <div className="text-bismuth-dim text-xs mt-0.5">Projects</div>
        </div>
        <button
          onClick={onOpenSettings}
          className="text-xs px-3 py-1.5 border border-bismuth-border text-bismuth-dim rounded hover:border-bismuth-accent hover:text-bismuth-text transition-colors font-mono"
        >
          ⚙ Settings
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-8">
        <div className="max-w-3xl mx-auto">

          {/* New Project card */}
          <button
            onClick={onNewProject}
            className="w-full border-2 border-dashed border-bismuth-border rounded-xl p-6 text-center hover:border-bismuth-accent hover:bg-bismuth-surface/50 transition-all group mb-6"
          >
            <div className="text-3xl mb-2 text-bismuth-dim group-hover:text-bismuth-accent transition-colors">+</div>
            <div className="text-bismuth-text group-hover:text-bismuth-accent font-medium transition-colors text-sm">New Project</div>
            <div className="text-bismuth-dim text-xs mt-1">Start a new development sprint</div>
          </button>

          {/* Projects list */}
          {loading ? (
            <div className="text-bismuth-dim text-sm text-center mt-12">Loading projects...</div>
          ) : projects.length === 0 ? (
            <div className="text-bismuth-dim text-sm text-center mt-12">
              No projects yet. Create your first one above.
            </div>
          ) : (
            <div className="space-y-3">
              {projects.map(project => {
                const progress = project.total_sprints > 0
                  ? Math.round((project.current_sprint / project.total_sprints) * 100)
                  : 0

                return (
                  <div key={project.id}
                    className="bg-bismuth-surface border border-bismuth-border rounded-xl p-5 hover:border-bismuth-accent/40 transition-colors"
                  >
                    <div className="flex items-start gap-4">
                      {/* Status dot */}
                      <div className={`w-2.5 h-2.5 rounded-full flex-shrink-0 mt-1.5 ${STATUS_DOT[project.status] || 'bg-bismuth-muted'}`} />

                      {/* Info */}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-3 mb-1">
                          <span className="text-bismuth-text font-medium truncate">{project.name}</span>
                          <span className="text-bismuth-dim text-xs font-mono flex-shrink-0">
                            {PHASE_LABEL[project.phase] || project.phase}
                          </span>
                        </div>

                        <div className="flex items-center gap-3 text-bismuth-dim text-xs">
                          {project.total_sprints > 0 && (
                            <span className="font-mono">
                              {project.current_sprint}/{project.total_sprints} sprints
                            </span>
                          )}
                          {project.created_at && (
                            <>
                              <span className="text-bismuth-border">·</span>
                              <span>{new Date(project.created_at).toLocaleDateString()}</span>
                            </>
                          )}
                          <span className="font-mono text-bismuth-muted">{project.id}</span>
                        </div>

                        {/* Progress bar */}
                        {project.total_sprints > 0 && (
                          <div className="mt-2 h-1 bg-bismuth-bg rounded-full overflow-hidden">
                            <div
                              className={`h-full rounded-full transition-all ${
                                project.phase === 'complete' ? 'bg-bismuth-green' : 'bg-bismuth-accent'
                              }`}
                              style={{ width: `${Math.min(progress, 100)}%` }}
                            />
                          </div>
                        )}
                      </div>

                      {/* Actions */}
                      <div className="flex items-center gap-2 flex-shrink-0">
                        {project.phase === 'complete' && (
                          <a
                            href={`${agentUrl}/projects/${project.id}/export`}
                            className="text-xs px-3 py-1.5 border border-bismuth-green/40 text-bismuth-green rounded hover:bg-bismuth-green/10 transition-colors"
                          >
                            ⬇ Export
                          </a>
                        )}
                        <button
                          onClick={() => handleOpen(project.id)}
                          disabled={loadingId === project.id}
                          className="text-xs px-3 py-1.5 border border-bismuth-border text-bismuth-dim rounded hover:border-bismuth-accent hover:text-bismuth-text transition-colors disabled:opacity-50"
                        >
                          {loadingId === project.id ? '...' : project.phase === 'complete' ? 'View' : 'Resume'}
                        </button>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
