import { useCallback, useEffect, useState } from 'react'
import { apiUrl } from '../lib/api'

type ResearchSession = {
  id: string
  topic: string
  status: 'planning' | 'searching' | 'synthesizing' | 'completed' | 'failed'
  total_sources: number
  total_queries: number
  queries_completed: number
  report_artifact_id: string | null
  error_message: string | null
  created_at: string | null
  completed_at: string | null
}

type DeepResearchProps = { onArtifactReady?: (artifactId: string) => void }

const STATUS_LABELS: Record<string, { label: string; color: string }> = {
  planning: { label: 'Generating research plan...', color: 'text-blue-400' },
  searching: { label: 'Searching the web...', color: 'text-blue-400' },
  synthesizing: { label: 'Synthesizing findings...', color: 'text-purple-400' },
  completed: { label: 'Research complete', color: 'text-emerald-400' },
  failed: { label: 'Research failed', color: 'text-red-400' },
}

export function DeepResearch({ onArtifactReady }: DeepResearchProps) {
  const [topic, setTopic] = useState('')
  const [sessions, setSessions] = useState<ResearchSession[]>([])
  const [activeSession, setActiveSession] = useState<ResearchSession | null>(null)
  const [starting, setStarting] = useState(false)

  const loadSessions = useCallback(async () => {
    try {
      const resp = await fetch(apiUrl('/api/research/'), { credentials: 'include' })
      const data = await resp.json()
      if (data.ok) {
        setSessions(data.sessions)
        if (!activeSession && data.sessions.length > 0) setActiveSession(data.sessions[0])
      }
    } catch {
      // silent
    }
  }, [activeSession])

  useEffect(() => {
    const t = window.setTimeout(() => { void loadSessions() }, 0)
    return () => window.clearTimeout(t)
  }, [loadSessions])

  useEffect(() => {
    if (!activeSession || ['completed', 'failed'].includes(activeSession.status)) return
    const interval = window.setInterval(() => { void loadSessions() }, 4000)
    return () => window.clearInterval(interval)
  }, [activeSession, loadSessions])

  const startResearch = async () => {
    if (!topic.trim()) return
    setStarting(true)
    try {
      await fetch(apiUrl('/api/research/start'), {
        method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ topic: topic.trim(), provider: 'google' }),
      })
      setTopic('')
      void loadSessions()
    } finally {
      setStarting(false)
    }
  }

  useEffect(() => {
    if (activeSession?.status === 'completed' && activeSession.report_artifact_id) {
      onArtifactReady?.(activeSession.report_artifact_id)
    }
  }, [activeSession, onArtifactReady])

  return (
    <div className='space-y-3 rounded-xl border border-[#2a2a2a] bg-[#1a1a1a] p-4'>
      <h3 className='text-sm font-semibold text-white'>Deep Research</h3>
      <div className='flex gap-2'>
        <input value={topic} onChange={(e) => setTopic(e.target.value)} placeholder='Research topic...' className='flex-1 rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-white' />
        <button type='button' onClick={() => void startResearch()} disabled={starting || !topic.trim()} className='rounded-lg bg-blue-600 px-3 py-2 text-xs text-white disabled:opacity-50'>
          {starting ? 'Starting...' : 'Start'}
        </button>
      </div>
      {activeSession && !['completed', 'failed'].includes(activeSession.status) && (
        <div className='rounded-xl border border-blue-900/50 bg-blue-900/10 p-4'>
          <span className={`text-xs ${STATUS_LABELS[activeSession.status]?.color || ''}`}>{STATUS_LABELS[activeSession.status]?.label}</span>
        </div>
      )}
      {sessions.length > 0 && <p className='text-xs text-zinc-500'>{sessions.length} research session(s)</p>}
    </div>
  )
}
