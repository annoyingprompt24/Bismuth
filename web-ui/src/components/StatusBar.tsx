'use client'

import { AgentState } from '@/hooks/useBismuthSocket'

const STATUS_CONFIG = {
  grey:   { label: 'Inactive',        dot: 'status-grey',   pulse: false },
  green:  { label: 'Running',         dot: 'status-green',  pulse: true  },
  yellow: { label: 'Issue Detected',  dot: 'status-yellow', pulse: true  },
  red:    { label: 'Critical Error',  dot: 'status-red',    pulse: true  },
  blue:   { label: 'Awaiting Input',  dot: 'status-blue',   pulse: true  },
}

const PHASE_LABELS: Record<string, string> = {
  setup:                    'Setup',
  planning:                 'Generating Roadmap',
  awaiting_roadmap_approval:'Roadmap Review',
  awaiting_sprint_approval: 'Sprint Plan Review',
  running:                  'Sprint Execution',
  paused:                   'Paused',
  complete:                 'Complete',
  error:                    'Error',
}

export default function StatusBar({ state, connected }: { state: AgentState | null, connected: boolean }) {
  const status = state?.status || 'grey'
  const config = STATUS_CONFIG[status]

  return (
    <div className="h-12 flex items-center justify-between px-5 bg-bismuth-surface border-b border-bismuth-border flex-shrink-0">
      {/* Left — Logo + project */}
      <div className="flex items-center gap-4">
        <span className="text-bismuth-accent font-mono font-medium tracking-widest text-sm">BISMUTH</span>
        {state?.project && (
          <>
            <span className="text-bismuth-border">|</span>
            <span className="text-bismuth-text text-sm">{state.project}</span>
          </>
        )}
      </div>

      {/* Centre — Phase */}
      <div className="text-bismuth-dim text-xs font-mono">
        {state ? PHASE_LABELS[state.phase] || state.phase : '—'}
      </div>

      {/* Right — Status + connection */}
      <div className="flex items-center gap-4">
        {state && (
          <>
            <span className="text-bismuth-dim text-xs">
              Sprint <span className="text-bismuth-text font-mono">{String(state.current_sprint).padStart(3, '0')}</span>
            </span>

            {state.yellow_cards > 0 && (
              <div className="flex items-center gap-1">
                {Array.from({ length: state.yellow_cards }).map((_, i) => (
                  <span key={i} className="text-bismuth-yellow text-xs">🟡</span>
                ))}
              </div>
            )}

            <div className="flex items-center gap-2">
              <span className={`status-dot ${config.dot} ${config.pulse ? 'animate-pulse-glow' : ''}`} />
              <span className="text-bismuth-dim text-xs">{config.label}</span>
            </div>
          </>
        )}

        <div className="flex items-center gap-1.5">
          <div className={`w-1.5 h-1.5 rounded-full ${connected ? 'bg-bismuth-green' : 'bg-bismuth-red'}`} />
          <span className="text-bismuth-dim text-xs">{connected ? 'Connected' : 'Disconnected'}</span>
        </div>
      </div>
    </div>
  )
}
