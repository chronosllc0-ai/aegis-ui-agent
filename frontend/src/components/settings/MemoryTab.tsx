import { useState } from 'react'
import { useMemory } from '../../hooks/useMemory'

const CATEGORIES = ['general', 'preference', 'fact', 'instruction', 'context'] as const

export function MemoryTab() {
  const { items, loading, error, load, create, remove } = useMemory()
  const [content, setContent] = useState('')
  const [category, setCategory] = useState<string>('general')
  const [importance, setImportance] = useState(0.5)

  const handleLoad = async () => {
    await load()
  }

  const handleCreate = async () => {
    const text = content.trim()
    if (!text) return
    await create(text, category, importance)
    setContent('')
  }

  return (
    <section className='space-y-3 rounded-xl border border-[#2a2a2a] bg-[#1a1a1a] p-3'>
      <div className='flex items-center justify-between'>
        <h3 className='text-sm font-semibold text-zinc-100'>Memory</h3>
        <button type='button' onClick={() => void handleLoad()} className='rounded border border-[#2a2a2a] px-2 py-1 text-xs text-zinc-300 hover:bg-zinc-800'>
          Refresh
        </button>
      </div>
      <div className='space-y-2 rounded border border-[#2a2a2a] bg-[#111] p-2'>
        <textarea
          value={content}
          onChange={(event) => setContent(event.target.value)}
          placeholder='Add a reusable memory for future tasks...'
          className='min-h-20 w-full rounded border border-[#2a2a2a] bg-[#1a1a1a] p-2 text-xs text-zinc-100'
        />
        <div className='flex flex-wrap gap-2'>
          <select value={category} onChange={(event) => setCategory(event.target.value)} className='rounded border border-[#2a2a2a] bg-[#1a1a1a] px-2 py-1 text-xs text-zinc-100'>
            {CATEGORIES.map((item) => (
              <option key={item} value={item}>{item}</option>
            ))}
          </select>
          <input
            type='number'
            min={0}
            max={1}
            step={0.1}
            value={importance}
            onChange={(event) => setImportance(Number(event.target.value))}
            className='w-24 rounded border border-[#2a2a2a] bg-[#1a1a1a] px-2 py-1 text-xs text-zinc-100'
          />
          <button type='button' onClick={() => void handleCreate()} className='rounded bg-blue-600 px-2 py-1 text-xs text-white hover:bg-blue-500'>
            Save memory
          </button>
        </div>
      </div>
      {loading && <p className='text-xs text-zinc-400'>Loading memories…</p>}
      {error && <p className='text-xs text-red-400'>{error}</p>}
      <div className='space-y-2'>
        {items.map((item) => (
          <div key={item.id} className='rounded border border-[#2a2a2a] bg-[#111] p-2'>
            <div className='flex items-center justify-between gap-2'>
              <span className='text-[10px] uppercase text-zinc-500'>{item.category}</span>
              <button type='button' onClick={() => void remove(item.id)} className='text-[10px] text-red-400 hover:text-red-300'>Delete</button>
            </div>
            <p className='mt-1 text-xs text-zinc-200'>{item.content}</p>
          </div>
        ))}
        {!loading && items.length === 0 && <p className='text-xs text-zinc-500'>No memories yet.</p>}
      </div>
    </section>
  )
}
