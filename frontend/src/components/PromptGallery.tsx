import { useCallback, useEffect, useState } from 'react'
import { apiUrl } from '../lib/api'

type Template = {
  id: string
  title: string
  description: string
  category: string
  tags: string[]
  prompt: string
  required_connectors: string[]
  expected_artifacts: string[]
  complexity: 'simple' | 'moderate' | 'complex'
  estimated_credits: number
}

type PromptGalleryProps = {
  onSelectTemplate: (prompt: string) => void
  onClose: () => void
}

const COMPLEXITY_COLORS: Record<string, string> = {
  simple: 'bg-emerald-900/30 text-emerald-400',
  moderate: 'bg-blue-900/30 text-blue-400',
  complex: 'bg-amber-900/30 text-amber-400',
}

export function PromptGallery({ onSelectTemplate, onClose }: PromptGalleryProps) {
  const [templates, setTemplates] = useState<Template[]>([])
  const [categories, setCategories] = useState<string[]>([])
  const [activeCategory, setActiveCategory] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [loading, setLoading] = useState(true)

  const fetchTemplates = useCallback(async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams()
      if (activeCategory) params.set('category', activeCategory)
      if (searchQuery) params.set('q', searchQuery)
      const queryString = params.toString()
      const endpoint = queryString ? `/api/gallery/?${queryString}` : '/api/gallery/'
      const resp = await fetch(apiUrl(endpoint), { credentials: 'include' })
      const data = await resp.json()
      if (data.ok) setTemplates(data.templates)
    } catch {
      // silent
    } finally {
      setLoading(false)
    }
  }, [activeCategory, searchQuery])

  const fetchCategories = useCallback(async () => {
    try {
      const resp = await fetch(apiUrl('/api/gallery/categories'), { credentials: 'include' })
      const data = await resp.json()
      if (data.ok) setCategories(data.categories)
    } catch {
      // silent
    }
  }, [])

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      void fetchCategories()
    }, 0)
    return () => window.clearTimeout(timeout)
  }, [fetchCategories])

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      void fetchTemplates()
    }, 0)
    return () => window.clearTimeout(timeout)
  }, [fetchTemplates])

  return (
    <div className='flex h-full flex-col rounded-2xl border border-[#2a2a2a] bg-[#1a1a1a]'>
      <div className='flex items-center justify-between border-b border-[#2a2a2a] px-6 py-4'>
        <div>
          <h2 className='text-lg font-semibold text-white'>Prompt Gallery</h2>
          <p className='mt-0.5 text-xs text-zinc-400'>Browse curated workflows and launch with one click</p>
        </div>
        <button type='button' onClick={onClose} className='text-zinc-500 hover:text-zinc-300'>
          ✕
        </button>
      </div>

      <div className='border-b border-[#2a2a2a] px-6 py-3'>
        <input
          type='text'
          placeholder='Search templates...'
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className='mb-3 w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-white placeholder-zinc-500 focus:border-blue-500 focus:outline-none'
        />
        <div className='flex flex-wrap gap-1.5'>
          <button
            type='button'
            onClick={() => setActiveCategory(null)}
            className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
              !activeCategory ? 'bg-blue-600 text-white' : 'bg-zinc-800 text-zinc-400 hover:bg-zinc-700'
            }`}
          >
            All
          </button>
          {categories.map((cat) => (
            <button
              key={cat}
              type='button'
              onClick={() => setActiveCategory(cat)}
              className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                activeCategory === cat ? 'bg-blue-600 text-white' : 'bg-zinc-800 text-zinc-400 hover:bg-zinc-700'
              }`}
            >
              {cat}
            </button>
          ))}
        </div>
      </div>

      <div className='flex-1 overflow-y-auto p-6'>
        {loading ? (
          <div className='flex items-center justify-center py-12'>
            <div className='h-5 w-5 animate-spin rounded-full border-2 border-blue-500 border-t-transparent' />
          </div>
        ) : templates.length === 0 ? (
          <p className='py-12 text-center text-sm text-zinc-500'>No templates found</p>
        ) : (
          <div className='grid gap-3 sm:grid-cols-2 lg:grid-cols-3'>
            {templates.map((t) => (
              <button
                key={t.id}
                type='button'
                onClick={() => onSelectTemplate(t.prompt)}
                className='group rounded-xl border border-zinc-800 bg-zinc-900/50 p-4 text-left transition-all hover:border-blue-600/50 hover:bg-zinc-900'
              >
                <div className='flex items-start justify-between'>
                  <h3 className='text-sm font-semibold text-white group-hover:text-blue-300'>{t.title}</h3>
                  <span
                    className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium ${COMPLEXITY_COLORS[t.complexity] || ''}`}
                  >
                    {t.complexity}
                  </span>
                </div>
                <p className='mt-1.5 line-clamp-2 text-xs text-zinc-400'>{t.description}</p>
                <div className='mt-3 flex flex-wrap gap-1'>
                  <span className='rounded bg-zinc-800 px-1.5 py-0.5 text-[10px] text-zinc-500'>{t.category}</span>
                  {t.tags.slice(0, 2).map((tag) => (
                    <span key={tag} className='rounded bg-zinc-800 px-1.5 py-0.5 text-[10px] text-zinc-500'>
                      {tag}
                    </span>
                  ))}
                </div>
                <div className='mt-2 flex items-center justify-between'>
                  <span className='text-[10px] text-zinc-600'>~{t.estimated_credits} credits</span>
                  {t.required_connectors.length > 0 && (
                    <span className='text-[10px] text-amber-500'>Requires: {t.required_connectors.join(', ')}</span>
                  )}
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
