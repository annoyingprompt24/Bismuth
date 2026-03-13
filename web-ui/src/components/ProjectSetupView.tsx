'use client'

import { useState } from 'react'
import yaml from 'js-yaml'

function ListInput({ field, label, items, onChange, onAdd, onRemove }: {
  field: string
  label: string
  items: string[]
  onChange: (index: number, value: string) => void
  onAdd: () => void
  onRemove: (index: number) => void
}) {
  return (
    <div className="mb-5">
      <label className="block text-bismuth-dim text-xs font-mono uppercase tracking-wider mb-2">{label}</label>
      {items.map((item, i) => (
        <div key={i} className="flex gap-2 mb-2">
          <input value={item}
            onChange={e => onChange(i, e.target.value)}
            className="flex-1 bg-bismuth-bg border border-bismuth-border rounded-lg px-3 py-2 text-bismuth-text text-sm focus:outline-none focus:border-bismuth-accent"
            placeholder={`${label} item ${i + 1}`} />
          <button onClick={() => onRemove(i)}
            className="text-bismuth-dim hover:text-bismuth-red px-2 text-lg">×</button>
        </div>
      ))}
      <button onClick={onAdd} className="text-bismuth-accent text-sm hover:underline">+ Add item</button>
    </div>
  )
}

const FORM_TEMPLATE = {
  project: {
    name: '',
    description: '',
    definition_of_done: [''],
    scope_boundaries: [''],
    constraints: [''],
    milestones: [''],
    sprints_per_iteration: 6,
    tech_stack: [''],
  }
}

export default function ProjectSetupView({ agentUrl }: { agentUrl: string }) {
  const [mode, setMode] = useState<'choose' | 'form' | 'upload'>('choose')
  const [form, setForm] = useState(FORM_TEMPLATE)
  const [uploadContent, setUploadContent] = useState('')
  const [yamlPreview, setYamlPreview] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const updateField = (field: string, value: any) => {
    setForm(prev => ({ project: { ...prev.project, [field]: value } }))
  }

  const updateListField = (field: string, index: number, value: string) => {
    const arr = [...(form.project as any)[field]]
    arr[index] = value
    updateField(field, arr)
  }

  const addListItem = (field: string) => {
    updateField(field, [...(form.project as any)[field], ''])
  }

  const removeListItem = (field: string, index: number) => {
    const arr = (form.project as any)[field].filter((_: any, i: number) => i !== index)
    updateField(field, arr)
  }

  const generateYaml = () => {
    const cleaned = {
      project: Object.fromEntries(
        Object.entries(form.project).map(([k, v]) => [
          k,
          Array.isArray(v) ? v.filter(Boolean) : v
        ])
      )
    }
    return yaml.dump(cleaned, { lineWidth: 80 })
  }

  const handleFormPreview = () => {
    setYamlPreview(generateYaml())
  }

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = (ev) => {
      const content = ev.target?.result as string
      setUploadContent(content)
      setYamlPreview(content)
    }
    reader.readAsText(file)
  }

  const handleSubmit = async () => {
    const content = mode === 'upload' ? uploadContent : generateYaml()
    if (!content.trim()) { setError('No YAML content to submit'); return }

    try { yaml.load(content) } catch (e) {
      setError(`Invalid YAML: ${e}`)
      return
    }

    setLoading(true)
    setError('')
    try {
      const res = await fetch(`${agentUrl}/project/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ yaml_content: content })
      })
      const data = await res.json()
      if (data.success) {
        window.location.reload()
      } else {
        setError(data.error || 'Failed to start project')
      }
    } catch (e) {
      setError('Could not connect to agent')
    } finally {
      setLoading(false)
    }
  }

  // ── Choose mode ───────────────────────────────────────────────────────────
  if (mode === 'choose') return (
    <div className="h-screen flex items-center justify-center bg-bismuth-bg">
      <div className="w-full max-w-lg text-center">
        <div className="text-3xl font-mono font-light tracking-widest text-bismuth-accent mb-2">BISMUTH</div>
        <div className="text-bismuth-dim text-sm mb-10">New Project — How would you like to define requirements?</div>

        <div className="grid grid-cols-2 gap-4">
          <button
            onClick={() => setMode('form')}
            className="bg-bismuth-surface border border-bismuth-border hover:border-bismuth-accent rounded-xl p-6 text-left transition-all group"
          >
            <div className="text-2xl mb-3">📝</div>
            <div className="text-bismuth-text font-medium mb-1 group-hover:text-bismuth-accent transition-colors">Web Form</div>
            <div className="text-bismuth-dim text-sm">Fill in a guided form — we'll generate the YAML for you</div>
          </button>

          <button
            onClick={() => setMode('upload')}
            className="bg-bismuth-surface border border-bismuth-border hover:border-bismuth-accent rounded-xl p-6 text-left transition-all group"
          >
            <div className="text-2xl mb-3">📄</div>
            <div className="text-bismuth-text font-medium mb-1 group-hover:text-bismuth-accent transition-colors">Upload YAML</div>
            <div className="text-bismuth-dim text-sm">Upload your own pre-formatted requirements YAML</div>
          </button>
        </div>
      </div>
    </div>
  )

  // ── Upload mode ───────────────────────────────────────────────────────────
  if (mode === 'upload') return (
    <div className="h-screen flex items-center justify-center bg-bismuth-bg p-6">
      <div className="w-full max-w-2xl">
        <button onClick={() => setMode('choose')} className="text-bismuth-dim text-sm hover:text-bismuth-text mb-6 flex items-center gap-1">← Back</button>
        <h2 className="text-bismuth-text text-xl font-medium mb-6">Upload Requirements YAML</h2>

        <div className="border-2 border-dashed border-bismuth-border rounded-xl p-8 text-center mb-4 hover:border-bismuth-accent transition-colors cursor-pointer"
          onClick={() => document.getElementById('yaml-upload')?.click()}>
          <input id="yaml-upload" type="file" accept=".yaml,.yml" onChange={handleFileUpload} className="hidden" />
          <div className="text-3xl mb-2">📂</div>
          <div className="text-bismuth-text mb-1">Click to upload or drag and drop</div>
          <div className="text-bismuth-dim text-sm">.yaml or .yml files</div>
        </div>

        {yamlPreview && (
          <pre className="bg-bismuth-surface border border-bismuth-border rounded-lg p-4 text-bismuth-dim font-mono text-xs overflow-auto max-h-48 mb-4">
            {yamlPreview}
          </pre>
        )}

        {error && <div className="mb-4 text-bismuth-red text-sm">{error}</div>}

        <button onClick={handleSubmit} disabled={loading || !uploadContent}
          className="w-full bg-bismuth-accent hover:bg-blue-500 disabled:bg-bismuth-muted text-white rounded-lg py-3 font-medium transition-colors">
          {loading ? 'Starting...' : 'Generate Roadmap →'}
        </button>
      </div>
    </div>
  )

  // ── Form mode ─────────────────────────────────────────────────────────────
  return (
    <div className="h-screen overflow-y-auto bg-bismuth-bg">
      <div className="max-w-2xl mx-auto py-10 px-6">
        <button onClick={() => setMode('choose')} className="text-bismuth-dim text-sm hover:text-bismuth-text mb-6 flex items-center gap-1">← Back</button>
        <h2 className="text-bismuth-text text-xl font-medium mb-8">Define Project Requirements</h2>

        <div className="mb-5">
          <label className="block text-bismuth-dim text-xs font-mono uppercase tracking-wider mb-2">Project Name *</label>
          <input value={form.project.name} onChange={e => updateField('name', e.target.value)}
            className="w-full bg-bismuth-bg border border-bismuth-border rounded-lg px-4 py-2.5 text-bismuth-text text-sm focus:outline-none focus:border-bismuth-accent"
            placeholder="My Project" />
        </div>

        <div className="mb-5">
          <label className="block text-bismuth-dim text-xs font-mono uppercase tracking-wider mb-2">Description *</label>
          <textarea value={form.project.description} onChange={e => updateField('description', e.target.value)}
            rows={3}
            className="w-full bg-bismuth-bg border border-bismuth-border rounded-lg px-4 py-2.5 text-bismuth-text text-sm focus:outline-none focus:border-bismuth-accent resize-none"
            placeholder="What are we building and why?" />
        </div>

        {(['definition_of_done', 'scope_boundaries', 'constraints', 'milestones', 'tech_stack'] as const).map(field => (
          <ListInput key={field} field={field}
            label={{ definition_of_done: 'Definition of Done', scope_boundaries: 'Scope Boundaries', constraints: 'Constraints', milestones: 'Suggested Milestones', tech_stack: 'Tech Stack' }[field]}
            items={(form.project as any)[field]}
            onChange={(i, v) => updateListField(field, i, v)}
            onAdd={() => addListItem(field)}
            onRemove={i => removeListItem(field, i)} />
        ))}

        <div className="mb-6">
          <label className="block text-bismuth-dim text-xs font-mono uppercase tracking-wider mb-2">
            Sprints per Iteration: <span className="text-bismuth-accent">{form.project.sprints_per_iteration}</span>
          </label>
          <input type="range" min={4} max={8} value={form.project.sprints_per_iteration}
            onChange={e => updateField('sprints_per_iteration', parseInt(e.target.value))}
            className="w-full accent-bismuth-accent" />
          <div className="flex justify-between text-bismuth-dim text-xs mt-1">
            <span>4 (faster checkpoints)</span><span>8 (longer iterations)</span>
          </div>
        </div>

        <div className="border-t border-bismuth-border pt-6">
          <button onClick={handleFormPreview}
            className="w-full border border-bismuth-border rounded-lg py-2.5 text-bismuth-dim hover:text-bismuth-text hover:border-bismuth-accent transition-colors mb-3 text-sm">
            Preview YAML
          </button>

          {yamlPreview && (
            <pre className="bg-bismuth-surface border border-bismuth-border rounded-lg p-4 text-bismuth-dim font-mono text-xs overflow-auto max-h-48 mb-4">
              {yamlPreview}
            </pre>
          )}

          {error && <div className="mb-4 text-bismuth-red text-sm">{error}</div>}

          <button onClick={handleSubmit} disabled={loading || !form.project.name}
            className="w-full bg-bismuth-accent hover:bg-blue-500 disabled:bg-bismuth-muted text-white rounded-lg py-3 font-medium transition-colors">
            {loading ? 'Generating Roadmap...' : 'Generate Roadmap →'}
          </button>
        </div>
      </div>
    </div>
  )
}
