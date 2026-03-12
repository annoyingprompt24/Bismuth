'use client'

import { useState } from 'react'

const AGENT_URL = process.env.NEXT_PUBLIC_AGENT_URL || 'http://localhost:5000'

export default function SetupView() {
  const [step, setStep] = useState<'keys' | 'github' | 'done'>('keys')
  const [anthropicKey, setAnthropicKey] = useState('')
  const [githubClientId, setGithubClientId] = useState('')
  const [githubClientSecret, setGithubClientSecret] = useState('')
  const [externalRepo, setExternalRepo] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async () => {
    if (!anthropicKey.trim()) {
      setError('Anthropic API key is required')
      return
    }
    setLoading(true)
    setError('')
    try {
      const res = await fetch(`${AGENT_URL}/setup/keys`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          anthropic_api_key: anthropicKey,
          github_client_id: githubClientId,
          github_client_secret: githubClientSecret,
          external_repo_url: externalRepo,
        })
      })
      const data = await res.json()
      if (data.success) {
        window.location.reload()
      } else {
        setError(data.error || 'Setup failed')
      }
    } catch (e) {
      setError('Could not connect to agent. Is it running?')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="h-screen flex items-center justify-center bg-bismuth-bg">
      <div className="w-full max-w-md">
        {/* Header */}
        <div className="text-center mb-10">
          <div className="text-4xl font-mono font-light tracking-widest text-bismuth-accent mb-2">BISMUTH</div>
          <div className="text-bismuth-dim text-sm">Recursive AI Development Pipeline</div>
        </div>

        {/* Card */}
        <div className="bg-bismuth-surface border border-bismuth-border rounded-xl p-8">
          <h2 className="text-bismuth-text font-medium text-lg mb-1">Initial Setup</h2>
          <p className="text-bismuth-dim text-sm mb-6">Configure your API credentials to get started. These are stored locally and never leave your machine.</p>

          {/* Anthropic Key */}
          <div className="mb-5">
            <label className="block text-bismuth-dim text-xs font-mono uppercase tracking-wider mb-2">
              Anthropic API Key <span className="text-bismuth-red">*</span>
            </label>
            <input
              type="password"
              value={anthropicKey}
              onChange={e => setAnthropicKey(e.target.value)}
              placeholder="sk-ant-..."
              className="w-full bg-bismuth-bg border border-bismuth-border rounded-lg px-4 py-2.5 text-bismuth-text font-mono text-sm focus:outline-none focus:border-bismuth-accent transition-colors"
            />
            <p className="text-bismuth-dim text-xs mt-1.5">
              Get yours at <a href="https://console.anthropic.com" target="_blank" className="text-bismuth-accent hover:underline">console.anthropic.com</a>
            </p>
          </div>

          {/* Divider */}
          <div className="border-t border-bismuth-border my-6" />

          {/* GitHub OAuth */}
          <div className="mb-5">
            <label className="block text-bismuth-dim text-xs font-mono uppercase tracking-wider mb-2">
              GitHub Client ID <span className="text-bismuth-dim">(optional)</span>
            </label>
            <input
              type="text"
              value={githubClientId}
              onChange={e => setGithubClientId(e.target.value)}
              placeholder="Oauth App Client ID"
              className="w-full bg-bismuth-bg border border-bismuth-border rounded-lg px-4 py-2.5 text-bismuth-text font-mono text-sm focus:outline-none focus:border-bismuth-accent transition-colors"
            />
          </div>

          <div className="mb-5">
            <label className="block text-bismuth-dim text-xs font-mono uppercase tracking-wider mb-2">
              GitHub Client Secret <span className="text-bismuth-dim">(optional)</span>
            </label>
            <input
              type="password"
              value={githubClientSecret}
              onChange={e => setGithubClientSecret(e.target.value)}
              placeholder="Client secret"
              className="w-full bg-bismuth-bg border border-bismuth-border rounded-lg px-4 py-2.5 text-bismuth-text font-mono text-sm focus:outline-none focus:border-bismuth-accent transition-colors"
            />
          </div>

          <div className="mb-6">
            <label className="block text-bismuth-dim text-xs font-mono uppercase tracking-wider mb-2">
              External Repo URL <span className="text-bismuth-dim">(optional)</span>
            </label>
            <input
              type="text"
              value={externalRepo}
              onChange={e => setExternalRepo(e.target.value)}
              placeholder="https://github.com/user/repo.git"
              className="w-full bg-bismuth-bg border border-bismuth-border rounded-lg px-4 py-2.5 text-bismuth-text font-mono text-sm focus:outline-none focus:border-bismuth-accent transition-colors"
            />
          </div>

          {error && (
            <div className="mb-4 px-4 py-3 bg-bismuth-red/10 border border-bismuth-red/30 rounded-lg text-bismuth-red text-sm">
              {error}
            </div>
          )}

          <button
            onClick={handleSubmit}
            disabled={loading || !anthropicKey.trim()}
            className="w-full bg-bismuth-accent hover:bg-blue-500 disabled:bg-bismuth-muted disabled:cursor-not-allowed text-white rounded-lg py-3 font-medium transition-colors"
          >
            {loading ? 'Saving...' : 'Save & Continue →'}
          </button>
        </div>

        <p className="text-center text-bismuth-dim text-xs mt-4">
          Credentials stored in <code className="text-bismuth-accent">/state/.env</code> — never committed to git
        </p>
      </div>
    </div>
  )
}
