'use client'

import { useState, useRef, useEffect } from 'react'
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

function TokenBadge({ stats }: { stats: NonNullable<AgentState['token_stats']> }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  const pct = stats.percent_used
  const colour = pct >= 80 ? 'text-bismuth-red' : pct >= 50 ? 'text-bismuth-yellow' : 'text-bismuth-green'
  const fmt = (n: number) => n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n)

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(o => !o)}
        className={`text-xs font-mono ${colour} hover:opacity-80 transition-opacity`}
        title="Click to see token breakdown"
      >
        {fmt(stats.session_total)} / {fmt(stats.limit_session)}
      </button>

      {open && (
        <div className="absolute right-0 top-6 z-50 bg-bismuth-surface border border-bismuth-border rounded-lg p-3 shadow-lg w-52 text-xs font-mono">
          <div className="text-bismuth-dim uppercase tracking-wider mb-2 text-[10px]">Token Usage</div>
          <div className="space-y-1.5">
            <div className="flex justify-between">
              <span className="text-bismuth-dim">Input</span>
              <span className="text-bismuth-text">{stats.session_input.toLocaleString()}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-bismuth-dim">Output</span>
              <span className="text-bismuth-text">{stats.session_output.toLocaleString()}</span>
            </div>
            <div className="border-t border-bismuth-border my-1" />
            <div className="flex justify-between">
              <span className="text-bismuth-dim">Total</span>
              <span className={colour}>{stats.session_total.toLocaleString()}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-bismuth-dim">Limit</span>
              <span className="text-bismuth-text">{stats.limit_session.toLocaleString()}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-bismuth-dim">Used</span>
              <span className={colour}>{pct}%</span>
            </div>
          </div>
          {/* Progress bar */}
          <div className="mt-2 h-1 bg-bismuth-border rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all ${pct >= 80 ? 'bg-bismuth-red' : pct >= 50 ? 'bg-bismuth-yellow' : 'bg-bismuth-green'}`}
              style={{ width: `${Math.min(pct, 100)}%` }}
            />
          </div>
        </div>
      )}
    </div>
  )
}

export default function StatusBar({ state, connected, agentUrl, onGoToProjects }: { state: AgentState | null, connected: boolean, agentUrl: string | null, onGoToProjects?: () => void }) {
  const status = state?.status || 'grey'
  const config = STATUS_CONFIG[status]

  return (
    <div className="h-12 flex items-center justify-between px-5 bg-bismuth-surface border-b border-bismuth-border flex-shrink-0">
      {/* Left — Logo + project */}
      <div className="flex items-center gap-4">
        {onGoToProjects && (
          <button onClick={onGoToProjects} className="text-bismuth-dim hover:text-bismuth-text text-xs transition-colors font-mono">
            ←
          </button>
        )}
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

            {state.token_stats && (
              <TokenBadge stats={state.token_stats} />
            )}

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

        {state?.project && agentUrl && (
          <a href={`${agentUrl}/project/export`}
            className="text-xs px-2.5 py-1 border border-bismuth-border text-bismuth-dim rounded hover:border-bismuth-accent hover:text-bismuth-text transition-colors font-mono">
            ⬇ Export
          </a>
        )}

        <div className="flex items-center gap-1.5">
          <div className={`w-1.5 h-1.5 rounded-full ${connected ? 'bg-bismuth-green' : 'bg-bismuth-red'}`} />
          <span className="text-bismuth-dim text-xs">{connected ? 'Connected' : 'Disconnected'}</span>
        </div>
      </div>
    </div>
  )
}
