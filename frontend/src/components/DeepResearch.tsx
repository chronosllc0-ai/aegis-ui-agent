import { useState } from 'react'
import { apiUrl } from '../lib/api'

type ResearchSession = {
  id: string
  topic: string
  status: string
  total_sources: number
  queries_completed: number
  total_queries: number
}

export function DeepResearch() {
  const [topic, setTopic] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [session, setSession] = useState<ResearchSession | null>(null)

  const start = async () => {
    const value = topic.trim()
    if (!value) return
    setLoading(true)
    setError(null)
    try {
      const response = await fetch(apiUrl('/api/research/'), {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ topic: value, provider: 'google' }),
      })
      const data = await response.json()
      if (!response.ok || !data?.ok) throw new Error(data?.detail ?? 'Failed to start research')
      setSession(data.session)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start research')
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className='space-y-2 rounded-xl border border-[#2a2a2a] bg-[#1a1a1a] p-3'>
      <h3 className='text-sm font-semibold text-zinc-100'>Deep Research</h3>
      <div className='flex gap-2'>
        <input value={topic} onChange={(event) => setTopic(event.target.value)} placeholder='Research topic...' className='w-full rounded border border-[#2a2a2a] bg-[#111] px-2 py-1 text-xs text-zinc-100' />
        <button type='button' onClick={() => void start()} className='rounded bg-blue-600 px-3 py-1 text-xs text-white hover:bg-blue-500'>Run</button>
      </div>
      {loading && <p className='text-xs text-zinc-400'>Running research…</p>}
      {error && <p className='text-xs text-red-400'>{error}</p>}
      {session && (
        <div className='rounded border border-[#2a2a2a] bg-[#111] p-2 text-xs text-zinc-300'>
          <p className='font-medium text-zinc-100'>{session.topic}</p>
          <p>Status: {session.status}</p>
          <p>Queries: {session.queries_completed}/{session.total_queries}</p>
          <p>Sources: {session.total_sources}</p>
        </div>
      )}
    </section>
  )
}
