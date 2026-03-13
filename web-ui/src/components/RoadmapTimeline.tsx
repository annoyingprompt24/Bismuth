'use client'

import { AgentState } from '@/hooks/useBismuthSocket'

const STATUS_COLOURS: Record<string, string> = {
  grey:     'border-bismuth-muted text-bismuth-grey',
  green:    'border-bismuth-green text-bismuth-green',
  yellow:   'border-bismuth-yellow text-bismuth-yellow',
  red:      'border-bismuth-red text-bismuth-red',
  blue:     'border-bismuth-blue text-bismuth-blue',
  complete: 'border-bismuth-green text-bismuth-green',
}

const STATUS_ICONS: Record<string, string> = {
  grey:     '○',
  green:    '◉',
  yellow:   '◉',
  red:      '◉',
  blue:     '◉',
  complete: '✓',
}

const STATUS_BG: Record<string, string> = {
  grey:     'bg-bismuth-muted/10',
  green:    'bg-bismuth-green/10',
  yellow:   'bg-bismuth-yellow/10',
  red:      'bg-bismuth-red/10',
  blue:     'bg-bismuth-blue/10',
  complete: 'bg-bismuth-green/10',
}

export default function RoadmapTimeline({
  roadmap,
  state,
  agentUrl,
  onAcceptRoadmap,
  onAcceptSprints,
  onResume,
}: {
  roadmap: any
  state: AgentState | null
  agentUrl: string | null
  onAcceptRoadmap: () => void
  onAcceptSprints: () => void
  onResume: () => void
}) {
  if (!roadmap) {
    return (
      <div className="p-6">
        <div className="text-bismuth-dim text-xs font-mono uppercase tracking-wider mb-4">Roadmap</div>
        <div className="text-bismuth-dim text-sm">Awaiting roadmap generation...</div>
      </div>
    )
  }

  const milestones = roadmap.milestones || []
  const sprints = roadmap.sprints || []
  const phase = state?.phase

  const sprintsByMilestone = (milestoneId: string) =>
    sprints.filter((s: any) => s.milestone_id === milestoneId)

  return (
    <div className="p-4">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <span className="text-bismuth-dim text-xs font-mono uppercase tracking-wider">Roadmap</span>
        {roadmap.project_name && (
          <span className="text-bismuth-accent text-xs font-mono">{roadmap.project_name}</span>
        )}
      </div>

      {/* Approval actions */}
      {phase === 'awaiting_roadmap_approval' && (
        <div className="mb-4 p-3 bg-bismuth-blue/10 border border-bismuth-blue/30 rounded-lg">
          <div className="text-bismuth-blue text-xs mb-2 font-medium">📋 Review & Accept Roadmap</div>
          <div className="flex gap-2">
            <button onClick={onAcceptRoadmap}
              className="flex-1 bg-bismuth-accent text-white rounded px-3 py-1.5 text-xs font-medium hover:bg-blue-500 transition-colors">
              Accept
            </button>
            <button className="flex-1 border border-bismuth-border text-bismuth-dim rounded px-3 py-1.5 text-xs hover:text-bismuth-text transition-colors">
              Realign
            </button>
          </div>
        </div>
      )}

      {phase === 'awaiting_sprint_approval' && (
        <div className="mb-4 p-3 bg-bismuth-blue/10 border border-bismuth-blue/30 rounded-lg">
          <div className="text-bismuth-blue text-xs mb-2 font-medium">🗂 Review & Accept Sprint Plan</div>
          <div className="flex gap-2">
            <button onClick={onAcceptSprints}
              className="flex-1 bg-bismuth-accent text-white rounded px-3 py-1.5 text-xs font-medium hover:bg-blue-500 transition-colors">
              Accept Sprints
            </button>
            <button className="flex-1 border border-bismuth-border text-bismuth-dim rounded px-3 py-1.5 text-xs hover:text-bismuth-text transition-colors">
              Revise
            </button>
          </div>
        </div>
      )}

      {phase === 'paused' && (
        <div className="mb-4 p-3 bg-bismuth-yellow/10 border border-bismuth-yellow/30 rounded-lg">
          <div className="text-bismuth-yellow text-xs mb-2 font-medium">⏸ Agent Paused</div>
          <button onClick={onResume}
            className="w-full bg-bismuth-green/20 border border-bismuth-green/40 text-bismuth-green rounded px-3 py-1.5 text-xs font-medium hover:bg-bismuth-green/30 transition-colors">
            Resume →
          </button>
        </div>
      )}

      {/* Milestone + sprint timeline */}
      <div className="space-y-1">
        {milestones.map((milestone: any, mi: number) => {
          const ms_sprints = sprintsByMilestone(milestone.id)
          const statusColour = STATUS_COLOURS[milestone.status] || STATUS_COLOURS.grey
          const statusBg = STATUS_BG[milestone.status] || STATUS_BG.grey
          const icon = STATUS_ICONS[milestone.status] || '○'

          return (
            <div key={milestone.id}>
              {/* Milestone row */}
              <div className={`flex items-start gap-3 p-3 rounded-lg border ${statusBg} ${statusColour} border-opacity-30`}>
                <div className="text-sm font-mono mt-0.5 w-4 flex-shrink-0">{icon}</div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-xs font-medium truncate">{milestone.title}</span>
                    <span className="text-xs font-mono flex-shrink-0 opacity-60">{milestone.id}</span>
                  </div>
                  {milestone.description && (
                    <div className="text-xs opacity-60 mt-0.5 line-clamp-2">{milestone.description}</div>
                  )}
                </div>
              </div>

              {/* Sprint rows for this milestone */}
              {ms_sprints.length > 0 && (
                <div className="ml-7 mt-1 space-y-1 mb-2">
                  {ms_sprints.map((sprint: any) => {
                    const sprintColour = STATUS_COLOURS[sprint.status] || STATUS_COLOURS.grey
                    const isCurrent = state?.current_sprint !== undefined &&
                      sprints.findIndex((s: any) => s.id === sprint.id) === state.current_sprint

                    return (
                      <div key={sprint.id}
                        className={`flex items-center gap-2 px-3 py-1.5 rounded border text-xs
                          ${isCurrent ? 'border-bismuth-green/50 bg-bismuth-green/5' : 'border-bismuth-border/50 bg-bismuth-bg/50'}
                          ${sprintColour}`}>
                        <span className="font-mono w-3 flex-shrink-0 opacity-60">
                          {sprint.status === 'complete' ? '✓' : sprint.status === 'green' ? '▶' : '·'}
                        </span>
                        <span className="flex-1 truncate opacity-80">{sprint.title}</span>
                        {sprint.commit_sha && (
                          <a href={sprint.gitea_url} target="_blank" rel="noopener noreferrer"
                            className="font-mono opacity-50 hover:opacity-100 transition-opacity flex-shrink-0"
                            title="View commit">
                            {sprint.commit_sha}
                          </a>
                        )}
                      </div>
                    )
                  })}
                </div>
              )}

              {/* Connector line between milestones */}
              {mi < milestones.length - 1 && (
                <div className="ml-4 w-px h-3 bg-bismuth-border mx-auto" />
              )}
            </div>
          )
        })}
      </div>

      {/* Summary stats */}
      {sprints.length > 0 && (
        <div className="mt-6 pt-4 border-t border-bismuth-border grid grid-cols-3 gap-2 text-center">
          <div>
            <div className="text-bismuth-green text-sm font-mono">
              {sprints.filter((s: any) => s.status === 'complete').length}
            </div>
            <div className="text-bismuth-dim text-xs">Done</div>
          </div>
          <div>
            <div className="text-bismuth-accent text-sm font-mono">
              {sprints.filter((s: any) => s.status === 'green').length}
            </div>
            <div className="text-bismuth-dim text-xs">Active</div>
          </div>
          <div>
            <div className="text-bismuth-dim text-sm font-mono">
              {sprints.filter((s: any) => s.status === 'grey').length}
            </div>
            <div className="text-bismuth-dim text-xs">Pending</div>
          </div>
        </div>
      )}

      {/* Prominent export button on completion */}
      {phase === 'complete' && agentUrl && (
        <div className="mt-4 p-3 bg-bismuth-green/10 border border-bismuth-green/30 rounded-lg">
          <div className="text-bismuth-green text-xs mb-2 font-medium">🎉 Project Complete</div>
          <a href={`${agentUrl}/project/export`}
            className="flex items-center justify-center gap-2 w-full bg-bismuth-green/20 border border-bismuth-green/40 text-bismuth-green rounded px-3 py-2 text-xs font-medium hover:bg-bismuth-green/30 transition-colors">
            ⬇ Export Project
          </a>
        </div>
      )}
    </div>
  )
}
