'use client'

import { useEffect, useState, useCallback, useRef } from 'react'
import { io, Socket } from 'socket.io-client'

export interface AgentState {
  initialised: boolean
  project: string | null
  phase: string
  current_sprint: number
  current_iteration: number
  yellow_cards: number
  status: 'grey' | 'green' | 'yellow' | 'red' | 'blue'
  awaiting_input: boolean
  input_prompt: string | null
}

export interface AgentMessage {
  type: 'assistant' | 'user' | 'system' | 'gate' | 'flag' | 'complete' | 'error'
  content: string
  ts?: string
}

export interface AgentLog {
  level: 'info' | 'warning' | 'error'
  content: string
  ts: string
}

export function useBismuthSocket() {
  const socketRef = useRef<Socket | null>(null)
  const [connected, setConnected] = useState(false)
  const [agentUrl, setAgentUrl] = useState<string | null>(null)
  const [state, setState] = useState<AgentState | null>(null)
  const [roadmap, setRoadmap] = useState<any>(null)
  const [messages, setMessages] = useState<AgentMessage[]>([])
  const [logs, setLogs] = useState<AgentLog[]>([])

  // Fetch runtime config from server-side API route
  // Avoids NEXT_PUBLIC_ compile-time bake-in entirely
  useEffect(() => {
    fetch('/api/config')
      .then(r => r.json())
      .then(cfg => setAgentUrl(cfg.agentUrl))
      .catch(() => setAgentUrl('http://localhost:3068'))
  }, [])

  // Connect to agent once URL is known
  useEffect(() => {
    if (!agentUrl) return

    const socket = io(agentUrl, { transports: ['websocket', 'polling'] })
    socketRef.current = socket

    socket.on('connect', () => setConnected(true))
    socket.on('disconnect', () => setConnected(false))
    socket.on('state_update', (data: AgentState) => setState(data))
    socket.on('roadmap_update', (data: any) => setRoadmap(data))
    socket.on('agent_message', (msg: AgentMessage) => {
      setMessages(prev => [...prev, { ...msg, ts: new Date().toISOString() }])
    })
    socket.on('agent_log', (log: AgentLog) => {
      setLogs(prev => [...prev.slice(-499), log])
    })

    fetch(`${agentUrl}/state`)
      .then(r => r.json())
      .then(d => setState(d))
      .catch(() => {})

    fetch(`${agentUrl}/roadmap`)
      .then(r => r.json())
      .then(d => { if (d && Object.keys(d).length > 0) setRoadmap(d) })
      .catch(() => {})

    return () => { socket.disconnect() }
  }, [agentUrl])

  const sendMessage = useCallback((message: string) => {
    socketRef.current?.emit('chat_message', { message })
    setMessages(prev => [...prev, {
      type: 'user',
      content: message,
      ts: new Date().toISOString()
    }])
  }, [])

  const sendBreak = useCallback(() => {
    if (!agentUrl) return
    fetch(`${agentUrl}/agent/break`, { method: 'POST' }).catch(() => {})
  }, [agentUrl])

  const sendResume = useCallback(() => {
    if (!agentUrl) return
    fetch(`${agentUrl}/agent/resume`, { method: 'POST' }).catch(() => {})
  }, [agentUrl])

  const acceptRoadmap = useCallback(() => {
    if (!agentUrl) return
    fetch(`${agentUrl}/project/accept-roadmap`, { method: 'POST' }).catch(() => {})
  }, [agentUrl])

  const acceptSprints = useCallback(() => {
    if (!agentUrl) return
    fetch(`${agentUrl}/project/accept-sprints`, { method: 'POST' }).catch(() => {})
  }, [agentUrl])

  const setupKeys = useCallback((payload: object) => {
    if (!agentUrl) return Promise.reject('No agent URL')
    return fetch(`${agentUrl}/setup/keys`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    }).then(r => r.json())
  }, [agentUrl])

  const startProject = useCallback((yamlContent: string) => {
    if (!agentUrl) return Promise.reject('No agent URL')
    return fetch(`${agentUrl}/project/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ yaml_content: yamlContent })
    }).then(r => r.json())
  }, [agentUrl])

  return {
    connected,
    agentUrl,
    state,
    roadmap,
    messages,
    logs,
    sendMessage,
    sendBreak,
    sendResume,
    acceptRoadmap,
    acceptSprints,
    setupKeys,
    startProject,
  }
}