import { Fragment, type ChangeEvent, type ReactNode, useEffect, useMemo, useState } from 'react'
import { LuDownload, LuFolder, LuLoader, LuSearch } from 'react-icons/lu'
import { apiUrl } from '../../lib/api'
import { useToast } from '../../hooks/useToast'

type WorkspaceFile = {
  name: string
  content: string
  updated_at: string | null
}

type WorkspaceFilesTabProps = {
  isAdmin?: boolean
}

const READ_ONLY_VIEW_MODES = ['preview', 'markdown'] as const
const EDITOR_VIEW_MODES = ['write', 'preview'] as const

function renderInlineMarkdown(text: string): ReactNode[] {
  const inlinePattern = /(`[^`]+`|\*\*[^*]+\*\*)/g
  const matches = text.split(inlinePattern).filter(Boolean)
  return matches.map((chunk, index) => {
    if (chunk.startsWith('`') && chunk.endsWith('`')) {
      return (
        <code key={`code-${index}`} className='rounded bg-zinc-800 px-1 py-0.5 text-[11px] text-zinc-100'>
          {chunk.slice(1, -1)}
        </code>
      )
    }
    if (chunk.startsWith('**') && chunk.endsWith('**')) {
      return <strong key={`strong-${index}`}>{chunk.slice(2, -2)}</strong>
    }
    return <Fragment key={`text-${index}`}>{chunk}</Fragment>
  })
}

function renderMarkdownPreview(markdown: string): ReactNode {
  const lines = markdown.split('\n')
  return (
    <div className='space-y-2'>
      {lines.map((line, index) => {
        const key = `line-${index}`
        if (!line.trim()) return <div key={key} className='h-2' />
        if (line.startsWith('### ')) return <h3 key={key} className='mt-4 text-sm font-semibold text-zinc-100'>{renderInlineMarkdown(line.slice(4))}</h3>
        if (line.startsWith('## ')) return <h2 key={key} className='mt-4 text-base font-semibold text-zinc-100'>{renderInlineMarkdown(line.slice(3))}</h2>
        if (line.startsWith('# ')) return <h1 key={key} className='mt-4 text-lg font-semibold text-zinc-50'>{renderInlineMarkdown(line.slice(2))}</h1>
        if (line.startsWith('- ')) return <p key={key} className='text-sm leading-6 text-zinc-200'>• {renderInlineMarkdown(line.slice(2))}</p>
        return <p key={key} className='text-sm leading-6 text-zinc-200'>{renderInlineMarkdown(line)}</p>
      })}
    </div>
  )
}

export function WorkspaceFilesTab({ isAdmin = false }: WorkspaceFilesTabProps) {
  const [files, setFiles] = useState<WorkspaceFile[]>([])
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [expanded, setExpanded] = useState<string>('AGENTS.md')
  const [viewMode, setViewMode] = useState<(typeof READ_ONLY_VIEW_MODES)[number]>('preview')
  const [editorMode, setEditorMode] = useState<(typeof EDITOR_VIEW_MODES)[number]>('write')
  const toast = useToast()

  useEffect(() => {
    void (async () => {
      setLoading(true)
      try {
        const endpoint = isAdmin ? '/api/admin/workspace-files' : '/api/workspace-files'
        const response = await fetch(apiUrl(endpoint), { credentials: 'include' })
        if (!response.ok) throw new Error(`HTTP ${response.status}`)
        const payload = (await response.json()) as { files?: WorkspaceFile[] }
        setFiles(payload.files ?? [])
      } catch {
        toast.error('Failed to load workspace files')
      } finally {
        setLoading(false)
      }
    })()
  }, [isAdmin, toast])

  const filteredFiles = useMemo(
    () => files.filter((file) => file.name.toLowerCase().includes(query.trim().toLowerCase())),
    [files, query],
  )

  const updateFileContent = (name: string, content: string) => {
    setFiles((prev) => prev.map((file) => (file.name === name ? { ...file, content } : file)))
  }

  const saveFile = async (name: string) => {
    if (!isAdmin) return
    const target = files.find((file) => file.name === name)
    if (!target) return
    setSaving(true)
    try {
      const response = await fetch(apiUrl('/api/admin/workspace-files'), {
        method: 'PATCH',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ files: { [name]: target.content } }),
      })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const payload = (await response.json()) as { files?: WorkspaceFile[] }
      setFiles(payload.files ?? files)
      toast.success(`${name} saved`)
    } catch {
      toast.error(`Failed to save ${name}`)
    } finally {
      setSaving(false)
    }
  }

  const uploadFile = async (event: ChangeEvent<HTMLInputElement>, fileName: string) => {
    const selected = event.target.files?.[0]
    if (!selected) return
    const text = await selected.text()
    updateFileContent(fileName, text)
    event.currentTarget.value = ''
  }

  if (loading) {
    return (
      <div className='flex items-center justify-center py-12'>
        <LuLoader className='h-5 w-5 animate-spin text-zinc-500' />
      </div>
    )
  }

  return (
    <section className='space-y-3 rounded-xl border border-[#2a2a2a] bg-[#1a1a1a] p-3'>
      <div>
        <h3 className='text-sm font-semibold text-zinc-100'>Workspace Files</h3>
        <p className='text-xs text-zinc-400'>Global markdown files populated into every Aegis runtime workspace.</p>
      </div>

      <div className='flex items-center gap-2 rounded-lg border border-[#2a2a2a] bg-[#111] px-2 py-1.5'>
        <LuSearch className='h-3.5 w-3.5 text-zinc-500' />
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder='Search workspace files…'
          className='w-full bg-transparent text-xs text-zinc-200 placeholder:text-zinc-500 focus:outline-none'
        />
      </div>

      <div className='space-y-2'>
        {filteredFiles.map((file) => {
          const isOpen = expanded === file.name
          return (
            <article key={file.name} className='rounded-lg border border-[#2a2a2a] bg-[#111]'>
              <button
                type='button'
                onClick={() => setExpanded((prev) => (prev === file.name ? '' : file.name))}
                className='flex w-full items-center justify-between px-3 py-2 text-left text-sm text-zinc-100 hover:bg-white/5'
              >
                <span className='inline-flex items-center gap-2'>
                  <LuFolder className='h-3.5 w-3.5 text-zinc-500' />
                  {file.name}
                </span>
                <span className='text-xs text-zinc-500'>{isOpen ? '▾' : '▸'}</span>
              </button>

              {isOpen && (
                <div className='border-t border-[#2a2a2a] p-3'>
                  {!isAdmin ? (
                    <>
                      <div className='mb-3 inline-flex rounded-lg border border-[#2a2a2a] bg-[#0f0f0f] p-1'>
                        {READ_ONLY_VIEW_MODES.map((mode) => (
                          <button
                            key={mode}
                            type='button'
                            onClick={() => setViewMode(mode)}
                            className={`rounded px-2 py-1 text-xs ${viewMode === mode ? 'bg-zinc-700 text-white' : 'text-zinc-400'}`}
                          >
                            {mode === 'preview' ? 'Preview' : 'Markdown'}
                          </button>
                        ))}
                      </div>
                      {viewMode === 'preview' ? (
                        <div className='max-w-none'>{renderMarkdownPreview(file.content)}</div>
                      ) : (
                        <pre className='max-h-96 overflow-auto rounded border border-[#2a2a2a] bg-[#0c0c0c] p-3 text-xs text-zinc-300'>{file.content}</pre>
                      )}
                    </>
                  ) : (
                    <>
                      <div className='mb-3 flex flex-wrap items-center justify-between gap-2'>
                        <div className='inline-flex rounded-lg border border-[#2a2a2a] bg-[#0f0f0f] p-1'>
                          {EDITOR_VIEW_MODES.map((mode) => (
                            <button
                              key={mode}
                              type='button'
                              onClick={() => setEditorMode(mode)}
                              className={`rounded px-2 py-1 text-xs ${editorMode === mode ? 'bg-zinc-700 text-white' : 'text-zinc-400'}`}
                            >
                              {mode === 'write' ? 'Write' : 'Preview'}
                            </button>
                          ))}
                        </div>

                        <label className='inline-flex cursor-pointer items-center gap-1 rounded border border-[#2a2a2a] px-2 py-1 text-xs text-zinc-300 hover:bg-white/5'>
                          <LuDownload className='h-3.5 w-3.5' /> Upload
                          <input
                            type='file'
                            accept='.md,text/markdown,text/plain'
                            className='hidden'
                            onChange={(event) => void uploadFile(event, file.name)}
                          />
                        </label>
                      </div>

                      {editorMode === 'write' ? (
                        <textarea
                          value={file.content}
                          onChange={(event) => updateFileContent(file.name, event.target.value)}
                          rows={14}
                          className='w-full rounded border border-[#2a2a2a] bg-[#0c0c0c] p-3 font-mono text-xs text-zinc-200 focus:border-zinc-500 focus:outline-none'
                        />
                      ) : (
                        <div className='max-w-none'>{renderMarkdownPreview(file.content)}</div>
                      )}

                      <div className='mt-3 flex items-center justify-between'>
                        <p className='text-[11px] text-zinc-500'>
                          Global file • updates apply to all users.
                        </p>
                        <button
                          type='button'
                          onClick={() => void saveFile(file.name)}
                          disabled={saving}
                          className='rounded bg-blue-600 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-blue-500 disabled:opacity-50'
                        >
                          {saving ? 'Saving…' : 'Save file'}
                        </button>
                      </div>
                    </>
                  )}
                </div>
              )}
            </article>
          )
        })}

        {filteredFiles.length === 0 && (
          <p className='rounded border border-dashed border-[#2a2a2a] p-3 text-xs text-zinc-500'>No workspace files found.</p>
        )}
      </div>
    </section>
  )
}
