import { useCallback, useEffect, useState } from 'react'
import { useArtifacts } from '../hooks/useArtifacts'
import type { ArtifactEntry } from '../hooks/useArtifacts'

type ArtifactPanelProps = {
  conversationId?: string
  isOpen: boolean
  onToggle: () => void
}

const TYPE_ICONS: Record<string, string> = {
  document: '📄', code: '💻', spreadsheet: '📊', image: '🖼', pdf: '📕', json: '{ }', html: '🌐',
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function ArtifactPanel({ conversationId, isOpen, onToggle }: ArtifactPanelProps) {
  const { artifacts, loading, fetchArtifacts, downloadArtifact, togglePin, deleteArtifact } = useArtifacts()
  const [expandedId, setExpandedId] = useState<string | null>(null)

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      if (isOpen) void fetchArtifacts(conversationId)
    }, 0)
    return () => window.clearTimeout(timeout)
  }, [isOpen, conversationId, fetchArtifacts])

  const handleDownload = useCallback((a: ArtifactEntry) => {
    void downloadArtifact(a.id, a.filename)
  }, [downloadArtifact])

  if (!isOpen) {
    return <button type='button' onClick={onToggle} className='fixed right-0 top-1/2 -translate-y-1/2 rounded-l-lg border border-r-0 border-[#2a2a2a] bg-[#1a1a1a] px-2 py-4 text-xs text-zinc-400 hover:bg-zinc-800'>📎</button>
  }

  return (
    <div className='flex h-full w-80 shrink-0 flex-col border-l border-[#2a2a2a] bg-[#1a1a1a]'>
      <div className='flex items-center justify-between border-b border-[#2a2a2a] px-4 py-3'>
        <h3 className='text-xs font-semibold uppercase tracking-wider text-zinc-400'>Artifacts</h3>
        <button type='button' onClick={onToggle} className='text-zinc-500 hover:text-zinc-300'>✕</button>
      </div>
      <div className='flex-1 overflow-y-auto p-3'>
        {loading ? <div className='flex justify-center py-8'><div className='h-4 w-4 animate-spin rounded-full border-2 border-blue-500 border-t-transparent' /></div> : (
          artifacts.length === 0 ? <p className='py-8 text-center text-xs text-zinc-600'>No artifacts yet</p> : (
            <div className='space-y-2'>
              {artifacts.map((a) => (
                <div key={a.id} className='group rounded-lg border border-zinc-800 bg-zinc-900/50 p-2.5'>
                  <div className='flex items-start gap-2'>
                    <span className='mt-0.5 text-sm'>{TYPE_ICONS[a.artifact_type] || '📎'}</span>
                    <div className='min-w-0 flex-1'>
                      <p className='truncate text-xs font-medium text-zinc-200'>{a.title}</p>
                      <span className='text-[10px] text-zinc-600'>{a.artifact_type} · {formatSize(a.file_size)}</span>
                    </div>
                    <div className='flex shrink-0 gap-0.5 opacity-0 group-hover:opacity-100'>
                      <button type='button' onClick={() => handleDownload(a)} className='rounded p-1 text-zinc-500 hover:bg-zinc-800 hover:text-blue-400'>↓</button>
                      <button type='button' onClick={() => void togglePin(a.id)} className={`rounded p-1 ${a.is_pinned ? 'text-amber-400' : 'text-zinc-600 hover:text-zinc-400'}`}>{a.is_pinned ? '★' : '☆'}</button>
                      <button type='button' onClick={() => void deleteArtifact(a.id)} className='rounded p-1 text-zinc-600 hover:bg-red-900/30 hover:text-red-400'>×</button>
                    </div>
                  </div>
                  {a.content_preview && <button type='button' onClick={() => setExpandedId(expandedId === a.id ? null : a.id)} className='mt-1.5 text-[10px] text-zinc-600 hover:text-zinc-400'>{expandedId === a.id ? 'Hide preview' : 'Show preview'}</button>}
                  {expandedId === a.id && a.content_preview && <pre className='mt-1.5 max-h-32 overflow-auto rounded-lg bg-zinc-800/50 p-2 text-[11px] text-zinc-400'>{a.content_preview}</pre>}
                </div>
              ))}
            </div>
          )
        )}
      </div>
    </div>
  )
}
