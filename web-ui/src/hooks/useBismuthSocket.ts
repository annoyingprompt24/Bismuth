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

const AGENT_URL = process.env.NEXT_PUBLIC_AGENT_URL || 'http://localhost:5000'

export function useBismuthSocket() {
  const socketRef = useRef<Socket | null>(null)
  const [connected, setConnected] = useState(false)
  const [state, setState] = useState<AgentState | null>(null)
  const [roadmap, setRoadmap] = useState<any>(null)
  const [messages, setMessages] = useState<AgentMessage[]>([])
  const [logs, setLogs] = useState<AgentLog[]>([])

  useEffect(() => {
    const socket = io(AGENT_URL, { transports: ['websocket', 'polling'] })
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

    // Fetch initial state
    fetch(`${AGENT_URL}/state`)
      .then(r => r.json())
      .then(d => setState(d))
      .catch(() => {})

    return () => { socket.disconnect() }
  }, [])

  const sendMessage = useCallback((message: string) => {
    socketRef.current?.emit('chat_message', { message })
    setMessages(prev => [...prev, {
      type: 'user',
      content: message,
      ts: new Date().toISOString()
    }])
  }, [])

  const sendBreak = useCallback(() => {
    fetch(`${AGENT_URL}/agent/break`, { method: 'POST' }).catch(() => {})
  }, [])

  const sendResume = useCallback(() => {
    fetch(`${AGENT_URL}/agent/resume`, { method: 'POST' }).catch(() => {})
  }, [])

  const acceptRoadmap = useCallback(() => {
    fetch(`${AGENT_URL}/project/accept-roadmap`, { method: 'POST' }).catch(() => {})
  }, [])

  const acceptSprints = useCallback(() => {
    fetch(`${AGENT_URL}/project/accept-sprints`, { method: 'POST' }).catch(() => {})
  }, [])

  return {
    connected,
    state,
    roadmap,
    messages,
    logs,
    sendMessage,
    sendBreak,
    sendResume,
    acceptRoadmap,
    acceptSprints,
  }
}
