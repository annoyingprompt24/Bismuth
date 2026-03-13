'use client'

import { useState, useEffect } from 'react'

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="mb-5">
      <label className="block text-bismuth-dim text-xs font-mono uppercase tracking-wider mb-2">{label}</label>
      {children}
    </div>
  )
}

function TextInput({ value, onChange, placeholder, type = 'text' }: {
  value: string; onChange: (v: string) => void; placeholder?: string; type?: string
}) {
  return (
    <input
      type={type}
      value={value}
      onChange={e => onChange(e.target.value)}
      placeholder={placeholder}
      className="w-full bg-bismuth-bg border border-bismuth-border rounded-lg px-4 py-2.5 text-bismuth-text font-mono text-sm focus:outline-none focus:border-bismuth-accent transition-colors"
    />
  )
}

function SecretField({ isSet, value, onChange, updating, onToggleUpdate, placeholder }: {
  isSet: boolean; value: string; onChange: (v: string) => void
  updating: boolean; onToggleUpdate: () => void; placeholder: string
}) {
  if (isSet && !updating) {
    return (
      <div className="flex items-center gap-3">
        <span className="flex-1 bg-bismuth-bg border border-bismuth-border rounded-lg px-4 py-2.5 text-bismuth-dim font-mono text-sm">
          ••••••••
        </span>
        <button onClick={onToggleUpdate} className="text-bismuth-accent text-sm hover:underline flex-shrink-0">
          Update
        </button>
      </div>
    )
  }
  return <TextInput type="password" value={value} onChange={onChange} placeholder={placeholder} />
}

export default function SettingsScreen({
  agentUrl,
  onBack,
}: {
  agentUrl: string
  onBack: () => void
}) {
  const [loading, setLoading]   = useState(true)
  const [saving, setSaving]     = useState(false)
  const [toast, setToast]       = useState('')
  const [toastOk, setToastOk]   = useState(true)

  // Secrets
  const [anthropicKeySet, setAnthropicKeySet]       = useState(false)
  const [anthropicKey, setAnthropicKey]             = useState('')
  const [updateAnthropicKey, setUpdateAnthropicKey] = useState(false)
  const [githubTokenSet, setGithubTokenSet]         = useState(false)
  const [githubToken, setGithubToken]               = useState('')
  const [updateGithubToken, setUpdateGithubToken]   = useState(false)

  // Plain fields
  const [githubUsername,       setGithubUsername]       = useState('')
  const [githubOrg,            setGithubOrg]            = useState('')
  const [defaultBranch,        setDefaultBranch]        = useState('main')
  const [sprintsPerIteration,  setSprintsPerIteration]  = useState(5)
  const [maxYellowCards,       setMaxYellowCards]       = useState(2)

  useEffect(() => {
    fetch(`${agentUrl}/settings`)
      .then(r => r.json())
      .then(data => {
        setAnthropicKeySet(data.anthropic_api_key_set)
        setGithubTokenSet(data.github_token_set)
        setGithubUsername(data.github_username || '')
        setGithubOrg(data.github_org || '')
        setDefaultBranch(data.default_branch || 'main')
        setSprintsPerIteration(data.sprints_per_iteration || 5)
        setMaxYellowCards(data.max_yellow_cards || 2)
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [agentUrl])

  const showToast = (msg: string, ok = true) => {
    setToast(msg)
    setToastOk(ok)
    setTimeout(() => setToast(''), 3000)
  }

  const handleSave = async () => {
    setSaving(true)
    const payload: Record<string, any> = {
      github_username:       githubUsername,
      github_org:            githubOrg,
      default_branch:        defaultBranch,
      sprints_per_iteration: sprintsPerIteration,
      max_yellow_cards:      maxYellowCards,
    }
    if (updateAnthropicKey && anthropicKey) payload.anthropic_api_key = anthropicKey
    if (updateGithubToken  && githubToken)  payload.github_token      = githubToken

    try {
      const res  = await fetch(`${agentUrl}/settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      const data = await res.json()
      if (data.success) {
        showToast('Settings saved')
        if (!anthropicKeySet && payload.anthropic_api_key) setAnthropicKeySet(true)
        if (!githubTokenSet  && payload.github_token)      setGithubTokenSet(true)
        setUpdateAnthropicKey(false); setAnthropicKey('')
        setUpdateGithubToken(false);  setGithubToken('')
      } else {
        showToast(data.error || 'Save failed', false)
      }
    } catch {
      showToast('Could not reach agent', false)
    } finally {
      setSaving(false)
    }
  }

  if (loading) return (
    <div className="h-screen flex items-center justify-center bg-bismuth-bg">
      <div className="text-bismuth-dim text-sm">Loading settings...</div>
    </div>
  )

  return (
    <div className="h-screen bg-bismuth-bg flex flex-col">
      {/* Header */}
      <div className="flex items-center gap-4 px-8 py-5 border-b border-bismuth-border flex-shrink-0">
        <button onClick={onBack} className="text-bismuth-dim hover:text-bismuth-text text-sm transition-colors">
          ← Back
        </button>
        <span className="text-bismuth-text font-medium text-sm">Settings</span>
      </div>

      {/* Toast */}
      {toast && (
        <div className={`fixed top-4 right-4 z-50 px-4 py-2 border rounded-lg text-sm transition-all ${
          toastOk
            ? 'bg-bismuth-green/20 border-bismuth-green/40 text-bismuth-green'
            : 'bg-bismuth-red/20 border-bismuth-red/40 text-bismuth-red'
        }`}>
          {toast}
        </div>
      )}

      <div className="flex-1 overflow-y-auto p-8">
        <div className="max-w-xl mx-auto">

          {/* API Keys */}
          <h3 className="text-bismuth-text font-medium text-sm mb-4">API Keys</h3>

          <Field label="Anthropic API Key">
            <SecretField
              isSet={anthropicKeySet}
              value={anthropicKey}
              onChange={setAnthropicKey}
              updating={updateAnthropicKey}
              onToggleUpdate={() => setUpdateAnthropicKey(true)}
              placeholder="sk-ant-..."
            />
          </Field>

          <Field label={<>GitHub Personal Access Token <span className="normal-case text-bismuth-muted">(optional)</span></>}>
            <SecretField
              isSet={githubTokenSet}
              value={githubToken}
              onChange={setGithubToken}
              updating={updateGithubToken}
              onToggleUpdate={() => setUpdateGithubToken(true)}
              placeholder="ghp_..."
            />
          </Field>

          <div className="border-t border-bismuth-border my-6" />

          {/* GitHub */}
          <h3 className="text-bismuth-text font-medium text-sm mb-4">GitHub</h3>

          <Field label="GitHub Username">
            <TextInput value={githubUsername} onChange={setGithubUsername} placeholder="your-username" />
          </Field>

          <Field label={<>GitHub Org <span className="normal-case text-bismuth-muted">(optional)</span></>}>
            <TextInput value={githubOrg} onChange={setGithubOrg} placeholder="my-org" />
          </Field>

          <Field label="Default Branch">
            <TextInput value={defaultBranch} onChange={setDefaultBranch} placeholder="main" />
          </Field>

          <div className="border-t border-bismuth-border my-6" />

          {/* Agent behaviour */}
          <h3 className="text-bismuth-text font-medium text-sm mb-4">Agent Behaviour</h3>

          <Field label={`Sprints per Iteration: ${sprintsPerIteration}`}>
            <input type="range" min={3} max={10} value={sprintsPerIteration}
              onChange={e => setSprintsPerIteration(parseInt(e.target.value))}
              className="w-full accent-bismuth-accent" />
            <div className="flex justify-between text-bismuth-dim text-xs mt-1">
              <span>3 (faster checkpoints)</span><span>10 (longer iterations)</span>
            </div>
          </Field>

          <Field label={`Max Yellow Cards: ${maxYellowCards}`}>
            <input type="range" min={1} max={5} value={maxYellowCards}
              onChange={e => setMaxYellowCards(parseInt(e.target.value))}
              className="w-full accent-bismuth-accent" />
            <div className="flex justify-between text-bismuth-dim text-xs mt-1">
              <span>1 (strict)</span><span>5 (lenient)</span>
            </div>
          </Field>

          <button
            onClick={handleSave}
            disabled={saving}
            className="w-full bg-bismuth-accent hover:bg-blue-500 disabled:bg-bismuth-muted text-white rounded-lg py-3 font-medium transition-colors mt-2"
          >
            {saving ? 'Saving...' : 'Save Settings'}
          </button>

        </div>
      </div>
    </div>
  )
}
