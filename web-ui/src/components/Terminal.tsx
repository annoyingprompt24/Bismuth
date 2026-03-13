'use client'

import { useEffect, useRef, useState } from 'react'
import { AgentState, AgentMessage, AgentLog } from '@/hooks/useBismuthSocket'

const MESSAGE_STYLES: Record<string, string> = {
  assistant: 'text-bismuth-text',
  user:      'text-bismuth-accent',
  system:    'text-bismuth-dim italic',
  gate:      'text-bismuth-blue',
  flag:      'text-bismuth-yellow',
  complete:  'text-bismuth-green',
  error:     'text-bismuth-red',
}

const MESSAGE_PREFIX: Record<string, string> = {
  assistant: 'bismuth  ',
  user:      'you    ',
  system:    'sys    ',
  gate:      'gate   ',
  flag:      '⚠ flag ',
  complete:  '✓ done ',
  error:     '✗ error',
}

export default function Terminal({
  messages,
  logs,
  state,
  onSend,
  onBreak,
  onResume,
}: {
  messages: AgentMessage[]
  logs: AgentLog[]
  state: AgentState | null
  onSend: (msg: string) => void
  onBreak: () => void
  onResume: () => void
}) {
  const [input, setInput] = useState('')
  const [tab, setTab] = useState<'chat' | 'logs'>('chat')
  const [sentFeedback, setSentFeedback] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const logsEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const isRunning = state?.phase === 'running' && !state?.awaiting_input
  const isAwaiting = state?.awaiting_input
  const isPaused = state?.phase === 'paused'

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs])

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const msg = input.trim()
    if (!msg) return

    if (msg.toUpperCase() === 'BREAK') {
      onBreak()
    } else {
      onSend(msg)
    }
    setInput('')
    setSentFeedback(true)
    setTimeout(() => setSentFeedback(false), 2000)
  }

  const inputDisabled = isRunning && !isAwaiting

  const inputPlaceholder = sentFeedback
    ? 'Message received — agent processing...'
    : isRunning
    ? 'Type BREAK to pause after current sprint...'
    : isAwaiting
    ? 'Type your response...'
    : isPaused
    ? 'Type a message or click Resume...'
    : 'Type a message...'

  return (
    <div className="flex flex-col h-full">
      {/* Tab bar */}
      <div className="flex items-center border-b border-bismuth-border bg-bismuth-surface px-4 flex-shrink-0">
        <button
          onClick={() => setTab('chat')}
          className={`px-4 py-2.5 text-xs font-mono border-b-2 transition-colors ${
            tab === 'chat' ? 'border-bismuth-accent text-bismuth-text' : 'border-transparent text-bismuth-dim hover:text-bismuth-text'
          }`}>
          Terminal
        </button>
        <button
          onClick={() => setTab('logs')}
          className={`px-4 py-2.5 text-xs font-mono border-b-2 transition-colors ${
            tab === 'logs' ? 'border-bismuth-accent text-bismuth-text' : 'border-transparent text-bismuth-dim hover:text-bismuth-text'
          }`}>
          Logs {logs.length > 0 && <span className="ml-1 text-bismuth-dim">({logs.length})</span>}
        </button>

        {/* Right-side controls */}
        <div className="ml-auto flex items-center gap-2">
          {isRunning && (
            <button onClick={onBreak}
              className="text-xs px-3 py-1 border border-bismuth-yellow/50 text-bismuth-yellow rounded hover:bg-bismuth-yellow/10 transition-colors font-mono">
              ⏸ BREAK
            </button>
          )}
          {isPaused && (
            <button onClick={onResume}
              className="text-xs px-3 py-1 border border-bismuth-green/50 text-bismuth-green rounded hover:bg-bismuth-green/10 transition-colors font-mono">
              ▶ RESUME
            </button>
          )}
        </div>
      </div>

      {/* Message / log area */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {tab === 'chat' && (
          <>
            {messages.length === 0 && (
              <div className="text-bismuth-dim text-xs font-mono text-center mt-8 opacity-50">
                Bismuth is ready. Waiting for project setup...
              </div>
            )}
            {messages.map((msg, i) => (
              <div key={i} className={`terminal-line animate-slide-in ${MESSAGE_STYLES[msg.type] || 'text-bismuth-text'}`}>
                <span className="text-bismuth-muted font-mono text-xs mr-3 select-none">
                  {MESSAGE_PREFIX[msg.type] || '       '}
                </span>
                <span style={{ whiteSpace: 'pre-wrap' }}>{msg.content}</span>
              </div>
            ))}
            <div ref={messagesEndRef} />
          </>
        )}

        {tab === 'logs' && (
          <>
            {logs.length === 0 && (
              <div className="text-bismuth-dim text-xs font-mono text-center mt-8 opacity-50">
                No logs yet
              </div>
            )}
            {logs.map((log, i) => (
              <div key={i} className={`terminal-line ${
                log.level === 'error' ? 'text-bismuth-red' :
                log.level === 'warning' ? 'text-bismuth-yellow' :
                'text-bismuth-dim'
              }`}>
                <span className="text-bismuth-muted mr-3 text-xs select-none">
                  {log.ts ? new Date(log.ts).toLocaleTimeString() : '--:--:--'}
                </span>
                <span className="mr-3 text-xs uppercase">[{log.level}]</span>
                {log.content}
              </div>
            ))}
            <div ref={logsEndRef} />
          </>
        )}
      </div>

      {/* Input */}
      <div className="border-t border-bismuth-border p-3 flex-shrink-0">
        {isAwaiting && state?.input_prompt && (
          <div className="mb-2 px-3 py-2 bg-bismuth-blue/10 border border-bismuth-blue/20 rounded text-bismuth-blue text-xs">
            {state.input_prompt}
          </div>
        )}

        <form onSubmit={handleSubmit} className="flex gap-2 items-center">
          <span className="text-bismuth-dim font-mono text-sm select-none">›</span>
          <input
            ref={inputRef}
            value={input}
            onChange={e => {
              // Only allow input if not in locked state, or if it's BREAK
              if (inputDisabled && e.target.value.toUpperCase() !== 'BREAK') {
                // Allow typing BREAK char by char
                const upper = e.target.value.toUpperCase()
                if (!'BREAK'.startsWith(upper)) return
              }
              setInput(e.target.value)
            }}
            placeholder={inputPlaceholder}
            className={`flex-1 bg-transparent font-mono text-sm focus:outline-none text-bismuth-text placeholder:text-bismuth-muted
              ${inputDisabled ? 'opacity-50' : ''}`}
            autoComplete="off"
            spellCheck={false}
          />
          <button type="submit"
            disabled={!input.trim()}
            className="text-bismuth-dim hover:text-bismuth-accent disabled:opacity-30 transition-colors font-mono text-xs">
            ↵
          </button>
        </form>
      </div>
    </div>
  )
}
