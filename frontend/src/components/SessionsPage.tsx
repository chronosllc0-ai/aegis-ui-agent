import { useEffect, useMemo, useState } from 'react'
import type { ServerSession } from '../hooks/useSessions'
import { HeaderBar, PanelCard } from './ui/DesignSystem'

export type SessionPageRow = {
  key: string
  label: string
  identity: string
  updated: string | null
  tokens: number
  kind: 'main' | 'channel' | 'heartbeat' | 'unknown'
}

type SessionsPageProps = {
  sessions: ServerSession[]
  onRefresh: () => Promise<void> | void
  onOpenSession: (sessionId: string) => void
}

const PAGE_SIZES = [10, 20, 50]

const estimateTokens = (text: string): number => Math.ceil(text.length / 4)

function formatUpdated(value: string | null): string {
  if (!value) return 'unknown'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'unknown'
  const diffMs = Date.now() - date.getTime()
  const diffMin = Math.round(diffMs / 60000)
  if (diffMin < 1) return 'just now'
  if (diffMin < 60) return `${diffMin}m ago`
  const diffHour = Math.round(diffMin / 60)
  if (diffHour < 24) return `${diffHour}h ago`
  const diffDay = Math.round(diffHour / 24)
  return `${diffDay}d ago`
}

export function SessionsPage({ sessions, onRefresh, onOpenSession }: SessionsPageProps) {
  const [search, setSearch] = useState('')
  const [filterActive, setFilterActive] = useState(true)
  const [filterGlobal, setFilterGlobal] = useState(true)
  const [filterUnknown, setFilterUnknown] = useState(true)
  const [activeOnly, setActiveOnly] = useState<'all' | 'active'>('all')
  const [page, setPage] = useState(0)
  const [pageSize, setPageSize] = useState(10)
  const [reasoningBySession, setReasoningBySession] = useState<Record<string, string>>({})

  const rows = useMemo<SessionPageRow[]>(() => {
    return sessions.map((session) => {
      const id = session.session_id
      const lowerId = id.toLowerCase()
      const kind: SessionPageRow['kind'] = lowerId.includes(':heartbeat')
        ? 'heartbeat'
        : lowerId.includes(':telegram:') || lowerId.includes(':discord:') || lowerId.includes(':slack:')
          ? 'channel'
          : lowerId.endsWith(':main')
            ? 'main'
            : 'unknown'
      return {
        key: id,
        label: session.title || (kind === 'heartbeat' ? 'heartbeat' : '(optional)'),
        identity: kind === 'channel' ? session.title || id : kind,
        updated: session.updated_at,
        tokens: estimateTokens(`${session.title ?? ''}${id}`),
        kind,
      }
    })
  }, [sessions])

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    const sorted = [...rows].sort((a, b) => (b.updated ?? '').localeCompare(a.updated ?? ''))
    return sorted.filter((row) => {
      if (!filterGlobal && (row.kind === 'main' || row.kind === 'heartbeat')) return false
      if (!filterUnknown && row.kind === 'unknown') return false
      if (!filterActive && row.kind !== 'heartbeat') return false
      if (activeOnly === 'active' && row.kind !== 'main' && row.kind !== 'channel' && row.kind !== 'heartbeat') return false
      if (!q) return true
      return `${row.key} ${row.label} ${row.kind} ${row.identity}`.toLowerCase().includes(q)
    })
  }, [activeOnly, filterActive, filterGlobal, filterUnknown, rows, search])

  useEffect(() => {
    setPage(0)
  }, [search, filterActive, filterGlobal, filterUnknown, activeOnly, pageSize])

  const total = filtered.length
  const start = page * pageSize
  const paged = filtered.slice(start, start + pageSize)
  const canPrev = page > 0
  const canNext = start + pageSize < total

  return (
    <div className='page-sections'>
      <HeaderBar
        left={<div><h2 className='text-lg font-semibold text-zinc-100'>Sessions</h2><p className='text-xs text-zinc-400'>Active sessions and defaults.</p></div>}
        right={<button type='button' onClick={() => void onRefresh()} className='rounded-md border border-zinc-700 px-3 py-1.5 text-xs text-zinc-200 hover:bg-zinc-800'>Refresh</button>}
      />

      <PanelCard className='space-y-4 p-3 sm:p-4'>
        <div className='flex flex-wrap items-center gap-2 text-xs'>
          <span className='text-zinc-500'>Store</span>
          <span className='rounded-full border border-zinc-700 px-2 py-0.5 text-zinc-200'>multiple</span>
          <label className='inline-flex items-center gap-1 text-zinc-300'><input type='checkbox' checked={filterActive} onChange={(e) => setFilterActive(e.target.checked)} />Active</label>
          <label className='inline-flex items-center gap-1 text-zinc-300'><input type='checkbox' checked={filterGlobal} onChange={(e) => setFilterGlobal(e.target.checked)} />Global</label>
          <label className='inline-flex items-center gap-1 text-zinc-300'><input type='checkbox' checked={filterUnknown} onChange={(e) => setFilterUnknown(e.target.checked)} />Unknown</label>
          <select value={activeOnly} onChange={(e) => setActiveOnly(e.target.value as 'all' | 'active')} className='rounded border border-zinc-700 bg-[#111] px-2 py-1 text-xs'>
            <option value='all'>All</option>
            <option value='active'>Active</option>
          </select>
        </div>

        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder='Filter by key, label, kind...'
          className='w-full rounded border border-zinc-700 bg-[#0f111a] px-3 py-2 text-sm text-zinc-200 outline-none'
        />

        <div className='overflow-x-auto'>
          <table className='min-w-[860px] w-full text-left text-xs'>
            <thead className='text-zinc-500'>
              <tr>
                <th className='py-2 pr-3'>Key</th>
                <th className='py-2 pr-3'>Label</th>
                <th className='py-2 pr-3'>Updated</th>
                <th className='py-2 pr-3'>Tokens</th>
                <th className='py-2 pr-3'>Compaction</th>
                <th className='py-2 pr-3'>Reasoning</th>
              </tr>
            </thead>
            <tbody>
              {paged.map((row) => (
                <tr key={row.key} className='border-t border-zinc-800 align-top'>
                  <td className='py-3 pr-3'>
                    <button type='button' className='text-red-300 hover:text-red-200' onClick={() => onOpenSession(row.key)}>{row.key}</button>
                    <div className='text-zinc-500'>{row.identity}</div>
                  </td>
                  <td className='py-3 pr-3'>
                    <input defaultValue={row.label} className='w-full rounded border border-zinc-700 bg-[#13151f] px-2 py-1 text-xs text-zinc-200' aria-label={`Label for ${row.key}`} />
                  </td>
                  <td className='py-3 pr-3 text-zinc-300'>{formatUpdated(row.updated)}</td>
                  <td className='py-3 pr-3 text-zinc-300'>{row.tokens.toLocaleString()} / 400000</td>
                  <td className='py-3 pr-3'><button type='button' className='rounded border border-zinc-700 px-2 py-1 text-zinc-200 hover:bg-zinc-800'>Show checkpoints</button></td>
                  <td className='py-3 pr-3'>
                    <select
                      value={reasoningBySession[row.key] ?? 'inherit'}
                      onChange={(e) => setReasoningBySession((prev) => ({ ...prev, [row.key]: e.target.value }))}
                      className='rounded border border-zinc-700 bg-[#111] px-2 py-1 text-xs text-zinc-100'
                    >
                      <option value='inherit'>inherit</option>
                      <option value='low'>low</option>
                      <option value='medium'>medium</option>
                      <option value='high'>high</option>
                    </select>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {paged.length === 0 && <div className='rounded border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-200'>Unable to load sessions view data or no rows match filters.</div>}
        </div>

        <div className='flex flex-wrap items-center justify-between gap-2 text-xs text-zinc-400'>
          <span>{total === 0 ? '0 rows' : `${start + 1}-${Math.min(total, start + pageSize)} of ${total} rows`}</span>
          <div className='flex items-center gap-2'>
            <select value={pageSize} onChange={(e) => setPageSize(Number(e.target.value))} className='rounded border border-zinc-700 bg-[#111] px-2 py-1 text-xs text-zinc-200'>
              {PAGE_SIZES.map((size) => <option key={size} value={size}>{size} per page</option>)}
            </select>
            <button type='button' disabled={!canPrev} onClick={() => setPage((prev) => Math.max(0, prev - 1))} className='rounded border border-zinc-700 px-2 py-1 disabled:opacity-50'>Previous</button>
            <button type='button' disabled={!canNext} onClick={() => setPage((prev) => prev + 1)} className='rounded border border-zinc-700 px-2 py-1 disabled:opacity-50'>Next</button>
          </div>
        </div>
      </PanelCard>
    </div>
  )
}
