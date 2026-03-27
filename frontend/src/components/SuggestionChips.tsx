import { useCallback, useEffect, useState } from 'react'
import { apiUrl } from '../lib/api'

type Suggestion = {
  id: string
  title: string
  category: string
}

type SuggestionChipsProps = {
  onSelectSuggestion: (templateId: string) => void
  onOpenGallery: () => void
}

export function SuggestionChips({ onSelectSuggestion, onOpenGallery }: SuggestionChipsProps) {
  const [suggestions, setSuggestions] = useState<Suggestion[]>([])

  const fetchSuggestions = useCallback(async () => {
    try {
      const resp = await fetch(apiUrl('/api/gallery/suggestions?limit=5'), { credentials: 'include' })
      const data = await resp.json()
      if (data.ok) setSuggestions(data.suggestions)
    } catch {
      // silent
    }
  }, [])

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      void fetchSuggestions()
    }, 0)
    return () => window.clearTimeout(timeout)
  }, [fetchSuggestions])

  if (suggestions.length === 0) return null

  return (
    <div className='flex items-center gap-2 overflow-x-auto px-2 py-1.5'>
      <button
        type='button'
        onClick={onOpenGallery}
        className='shrink-0 rounded-full border border-blue-600/50 bg-blue-900/20 px-3 py-1 text-xs font-medium text-blue-300 hover:bg-blue-900/40'
      >
        From the gallery
      </button>
      {suggestions.map((s) => (
        <button
          key={s.id}
          type='button'
          onClick={() => onSelectSuggestion(s.id)}
          className='shrink-0 rounded-full border border-zinc-700 bg-zinc-800 px-3 py-1 text-xs text-zinc-400 hover:border-zinc-600 hover:text-zinc-300'
          title={s.category}
        >
          {s.title}
        </button>
      ))}
    </div>
  )
}
