import { useEffect, useMemo, useRef, useState } from 'react'
import { FiCheck, FiChevronDown, FiSearch, FiX } from 'react-icons/fi'
import { PanelCard } from './ui/DesignSystem'

type SessionChannel = 'chat' | 'browser' | 'system'
type SessionStatus = 'active' | 'idle'

export interface SessionSwitcherItem {
  id: string
  label: string
  channel: SessionChannel
  status: SessionStatus
  detail?: string
  group?: 'main' | 'channels' | 'other'
}

interface SessionSwitcherProps {
  sessions: SessionSwitcherItem[]
  selectedSessionId: string | null | undefined
  onSelect: (sessionId: string) => void
}

function RadioItem({ item, selected, onSelect }: { item: SessionSwitcherItem; selected: boolean; onSelect: (id: string) => void }) {
  return (
    <button
      type='button'
      onClick={() => onSelect(item.id)}
      className={`flex w-full items-center gap-3 rounded-xl px-3 py-3 text-left transition ${selected ? 'bg-[#2a2d36]' : 'hover:bg-[#1a1d28]'}`}
      role='radio'
      aria-checked={selected}
    >
      <div className={`h-6 w-6 rounded-full border ${selected ? 'border-indigo-300' : 'border-zinc-500'} flex items-center justify-center`}>
        <div className={`h-3 w-3 rounded-full ${selected ? 'bg-indigo-300' : 'bg-transparent'}`} />
      </div>
      <div className='min-w-0 flex-1'>
        <p className='truncate text-base text-zinc-100'>{item.label}</p>
        {item.detail && <p className='truncate text-xs text-zinc-400'>{item.detail}</p>}
      </div>
      {selected && <FiCheck className='h-4 w-4 text-indigo-300' aria-hidden='true' />}
    </button>
  )
}

export function SessionSwitcher({ sessions, selectedSessionId, onSelect }: SessionSwitcherProps) {
  const [openDesktop, setOpenDesktop] = useState(false)
  const [openMobile, setOpenMobile] = useState(false)
  const [query, setQuery] = useState('')
  const desktopRef = useRef<HTMLDivElement>(null)

  const selectedSession = useMemo(() => sessions.find((session) => session.id === selectedSessionId) ?? sessions[0], [sessions, selectedSessionId])

  const filteredSessions = useMemo(() => {
    const q = query.trim().toLowerCase()
    const list = !q
      ? sessions
      : sessions.filter((session) => `${session.label} ${session.id} ${session.detail ?? ''}`.toLowerCase().includes(q))
    return {
      main: list.filter((item) => item.group === 'main'),
      channels: list.filter((item) => item.group === 'channels'),
      other: list.filter((item) => !item.group || item.group === 'other'),
    }
  }, [query, sessions])

  useEffect(() => {
    const onDocClick = (event: MouseEvent) => {
      if (desktopRef.current && !desktopRef.current.contains(event.target as Node)) setOpenDesktop(false)
    }
    document.addEventListener('mousedown', onDocClick)
    return () => document.removeEventListener('mousedown', onDocClick)
  }, [])

  if (sessions.length === 0 || !selectedSession) return null

  const closeAll = () => {
    setOpenDesktop(false)
    setOpenMobile(false)
    setQuery('')
  }

  const grouped = (groupLabel: string, rows: SessionSwitcherItem[]) => {
    if (rows.length === 0) return null
    return (
      <div className='space-y-1'>
        <p className='px-1 text-xs uppercase tracking-wide text-zinc-500'>{groupLabel}</p>
        <div role='radiogroup' className='space-y-1'>
          {rows.map((item) => (
            <RadioItem key={item.id} item={item} selected={selectedSession.id === item.id} onSelect={(id) => { onSelect(id); closeAll() }} />
          ))}
        </div>
      </div>
    )
  }

  const listBody = (
    <PanelCard className='space-y-3 p-3 shadow-[var(--ds-shadow-elevated)]'>
      <div className='flex items-center gap-2 rounded-lg border border-zinc-700 bg-[#131722] px-2 py-2'>
        <FiSearch className='h-3.5 w-3.5 text-zinc-500' />
        <input value={query} onChange={(e) => setQuery(e.target.value)} className='w-full bg-transparent text-xs text-zinc-100 outline-none' placeholder='Filter sessions' />
      </div>
      {grouped('main', filteredSessions.main)}
      {grouped('channels', filteredSessions.channels)}
      {grouped('other', filteredSessions.other)}
    </PanelCard>
  )

  return (
    <>
      <div ref={desktopRef} className='relative hidden sm:block'>
        <button type='button' onClick={() => setOpenDesktop((v) => !v)} className='flex min-w-[220px] max-w-[320px] items-center gap-2 rounded-xl border border-zinc-700 bg-[#141823] px-3 py-2 text-left'>
          <div className='min-w-0 flex-1'>
            <p className='truncate text-sm text-zinc-100'>{selectedSession.label}</p>
            <p className='truncate text-[11px] text-zinc-500'>{selectedSession.detail ?? selectedSession.id}</p>
          </div>
          <FiChevronDown className={`h-4 w-4 text-zinc-400 transition-transform ${openDesktop ? 'rotate-180' : ''}`} />
        </button>
        {openDesktop && <div className='absolute left-0 top-full z-30 mt-2 w-[420px]'>{listBody}</div>}
      </div>

      <div className='sm:hidden'>
        <button type='button' onClick={() => setOpenMobile(true)} className='flex max-w-[78vw] items-center gap-2 rounded-xl border border-zinc-700 bg-[#141823] px-3 py-2 text-left'>
          <div className='min-w-0 flex-1'><p className='truncate text-sm text-zinc-100'>{selectedSession.label}</p></div>
          <FiChevronDown className='h-4 w-4 text-zinc-500' />
        </button>
      </div>

      {openMobile && (
        <div className='fixed inset-0 z-50 bg-black/60 sm:hidden'>
          <div className='absolute inset-x-0 bottom-0 rounded-t-3xl border border-zinc-700 bg-[#181b25] p-3'>
            <div className='mb-3 flex items-center justify-between'>
              <p className='text-sm font-semibold text-zinc-100'>Switch session</p>
              <button type='button' onClick={closeAll} className='rounded-md border border-zinc-700 p-1.5 text-zinc-300'><FiX className='h-4 w-4' /></button>
            </div>
            {listBody}
          </div>
        </div>
      )}
    </>
  )
}
