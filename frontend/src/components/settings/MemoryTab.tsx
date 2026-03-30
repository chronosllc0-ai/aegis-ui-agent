import { useCallback, useEffect, useState } from 'react'
import { useMemory } from '../../hooks/useMemory'
import type { MemoryEntry } from '../../hooks/useMemory'

const CATEGORIES = ['general', 'preference', 'fact', 'instruction', 'context'] as const

const CATEGORY_COLORS: Record<string, string> = {
  general: 'bg-zinc-700 text-zinc-300',
  preference: 'bg-purple-900/40 text-purple-300',
  fact: 'bg-blue-900/40 text-blue-300',
  instruction: 'bg-amber-900/40 text-amber-300',
  context: 'bg-emerald-900/40 text-emerald-300',
}

export function MemoryTab() {
  const { memories, stats, loading, error, fetchMemories, fetchStats, createMemory, updateMemory, deleteMemory, searchMemories } = useMemory()
  const [activeCategory, setActiveCategory] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<MemoryEntry[] | null>(null)
  const [newContent, setNewContent] = useState('')
  const [newCategory, setNewCategory] = useState<string>('general')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editContent, setEditContent] = useState('')
  const [creating, setCreating] = useState(false)

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      void fetchMemories(activeCategory || undefined)
      void fetchStats()
    }, 0)
    return () => window.clearTimeout(timeout)
  }, [fetchMemories, fetchStats, activeCategory])

  const handleSearch = useCallback(async () => {
    if (!searchQuery.trim()) {
      setSearchResults(null)
      return
    }
    const results = await searchMemories(searchQuery, activeCategory || undefined)
    setSearchResults(results)
  }, [searchQuery, activeCategory, searchMemories])

  const handleCreate = async () => {
    if (!newContent.trim()) return
    setCreating(true)
    const result = await createMemory(newContent.trim(), newCategory)
    if (result) {
      setNewContent('')
      await fetchStats()
    }
    setCreating(false)
  }

  const handleDelete = async (id: string) => {
    await deleteMemory(id)
    await fetchStats()
  }

  const handleTogglePin = async (memory: MemoryEntry) => {
    await updateMemory(memory.id, { is_pinned: !memory.is_pinned })
  }

  const handleSaveEdit = async (id: string) => {
    if (!editContent.trim()) return
    await updateMemory(id, { content: editContent.trim() })
    setEditingId(null)
    setEditContent('')
  }

  const displayMemories = searchResults ?? memories

  return (
    <div className='space-y-6'>
      {stats && (
        <div className='flex gap-4 rounded-xl border border-[#2a2a2a] bg-[#1a1a1a] p-4'>
          <div><span className='text-lg font-semibold text-white'>{stats.total_memories}</span><span className='ml-1 text-xs text-zinc-500'>memories</span></div>
          <div><span className='text-lg font-semibold text-white'>{stats.pinned_memories}</span><span className='ml-1 text-xs text-zinc-500'>pinned</span></div>
        </div>
      )}

      <div className='rounded-xl border border-[#2a2a2a] bg-[#1a1a1a] p-4'>
        <h4 className='mb-2 text-xs font-semibold uppercase tracking-wider text-zinc-400'>Add Memory</h4>
        <textarea value={newContent} onChange={(e) => setNewContent(e.target.value)} placeholder='Tell Aegis something to remember...' className='mb-2 w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-white placeholder-zinc-500 focus:border-blue-500 focus:outline-none' rows={2} />
        <div className='flex items-center gap-2'>
          <select value={newCategory} onChange={(e) => setNewCategory(e.target.value)} className='rounded-lg border border-zinc-700 bg-zinc-800 px-2 py-1.5 text-xs text-zinc-300'>
            {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <div className='flex-1' />
          <button type='button' onClick={handleCreate} disabled={creating || !newContent.trim()} className='rounded-lg bg-blue-600 px-4 py-1.5 text-xs font-medium text-white hover:bg-blue-500 disabled:opacity-50'>
            {creating ? 'Saving...' : 'Save Memory'}
          </button>
        </div>
      </div>

      <div className='flex items-center gap-2'>
        <input type='text' value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && void handleSearch()} placeholder='Search memories semantically...' className='flex-1 rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-white placeholder-zinc-500 focus:border-blue-500 focus:outline-none' />
        <button type='button' onClick={() => void handleSearch()} className='rounded-lg bg-zinc-700 px-3 py-2 text-xs text-zinc-300 hover:bg-zinc-600'>Search</button>
      </div>

      <div className='flex gap-1.5'>
        <button type='button' onClick={() => setActiveCategory(null)} className={`rounded-full px-3 py-1 text-xs font-medium ${!activeCategory ? 'bg-blue-600 text-white' : 'bg-zinc-800 text-zinc-400 hover:bg-zinc-700'}`}>All</button>
        {CATEGORIES.map((cat) => (
          <button key={cat} type='button' onClick={() => setActiveCategory(cat)} className={`rounded-full px-3 py-1 text-xs font-medium ${activeCategory === cat ? 'bg-blue-600 text-white' : 'bg-zinc-800 text-zinc-400 hover:bg-zinc-700'}`}>{cat}</button>
        ))}
      </div>

      {error && <p className='text-sm text-red-400'>{error}</p>}
      {loading ? (
        <div className='flex justify-center py-8'><div className='h-5 w-5 animate-spin rounded-full border-2 border-blue-500 border-t-transparent' /></div>
      ) : displayMemories.length === 0 ? (
        <p className='py-8 text-center text-sm text-zinc-500'>No memories yet.</p>
      ) : (
        <div className='space-y-2'>
          {displayMemories.map((m) => (
            <div key={m.id} className='group rounded-xl border border-zinc-800 bg-zinc-900/50 p-3'>
              <div className='flex items-start gap-2'>
                <button type='button' onClick={() => void handleTogglePin(m)} className={`mt-0.5 text-sm ${m.is_pinned ? 'text-amber-400' : 'text-zinc-600 hover:text-zinc-400'}`}>{m.is_pinned ? '★' : '☆'}</button>
                <div className='min-w-0 flex-1'>
                  {editingId === m.id ? (
                    <div className='space-y-2'>
                      <textarea value={editContent} onChange={(e) => setEditContent(e.target.value)} className='w-full rounded-lg border border-zinc-700 bg-zinc-800 px-2 py-1.5 text-sm text-white focus:border-blue-500 focus:outline-none' rows={3} />
                      <button type='button' onClick={() => void handleSaveEdit(m.id)} className='rounded bg-blue-600 px-3 py-1 text-xs text-white hover:bg-blue-500'>Save</button>
                    </div>
                  ) : (
                    <p className='text-sm text-zinc-200'>{m.content}</p>
                  )}
                  <div className='mt-1.5 flex items-center gap-2'>
                    <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${CATEGORY_COLORS[m.category] || ''}`}>{m.category}</span>
                    <span className='text-[10px] text-zinc-700'>{m.access_count} recalls</span>
                  </div>
                </div>
                <div className='flex shrink-0 gap-1 opacity-0 group-hover:opacity-100'>
                  <button type='button' onClick={() => { setEditingId(m.id); setEditContent(m.content) }} className='text-xs text-zinc-500 hover:text-zinc-300'>Edit</button>
                  <button type='button' onClick={() => void handleDelete(m.id)} className='text-xs text-red-400 hover:text-red-300'>Del</button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
