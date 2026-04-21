import { useEffect, useMemo, useRef, useState } from 'react'
import { FiCheck, FiChevronDown, FiMonitor, FiSearch, FiSmartphone, FiX } from 'react-icons/fi'
import { PanelCard, StatusBadge } from './ui/DesignSystem'

type SessionChannel = 'chat' | 'browser' | 'system'
type SessionStatus = 'active' | 'idle'

export interface SessionSwitcherItem {
  id: string
  label: string
  channel: SessionChannel
  status: SessionStatus
}

interface SessionSwitcherProps {
  sessions: SessionSwitcherItem[]
  selectedSessionId: string | null | undefined
  onSelect: (sessionId: string) => void
}

const channelLabel: Record<SessionChannel, string> = {
  chat: 'Chat',
  browser: 'Browser',
  system: 'System',
}

function SessionRow({
  item,
  selected,
  onSelect,
}: {
  item: SessionSwitcherItem
  selected: boolean
  onSelect: (id: string) => void
}) {
  return (
    <button
      type='button'
      onClick={() => onSelect(item.id)}
      className={`group flex w-full items-center gap-2 rounded-lg border px-2.5 py-2 text-left transition-colors cursor-pointer ${
        selected
          ? 'border-cyan-500/40 bg-cyan-500/10'
          : 'border-transparent bg-[#141414] hover:border-[#2a2a2a] hover:bg-[#181818]'
      }`}
    >
      <span className={`h-2 w-2 rounded-full ${item.status === 'active' ? 'bg-emerald-400' : 'bg-zinc-500'}`} aria-hidden='true' />
      <div className='min-w-0 flex-1'>
        <p className='truncate text-sm text-zinc-100'>{item.label}</p>
        <p className='truncate text-[11px] text-zinc-500'>ID: {item.id}</p>
      </div>
      <StatusBadge label={channelLabel[item.channel]} tone={item.channel === 'chat' ? 'info' : item.channel === 'browser' ? 'warning' : 'default'} />
      {selected && <FiCheck className='h-3.5 w-3.5 text-cyan-300' aria-hidden='true' />}
    </button>
  )
}

export function SessionSwitcher({ sessions, selectedSessionId, onSelect }: SessionSwitcherProps) {
  const [openDesktop, setOpenDesktop] = useState(false)
  const [openMobile, setOpenMobile] = useState(false)
  const [query, setQuery] = useState('')
  const desktopRef = useRef<HTMLDivElement>(null)

  const selectedSession = useMemo(
    () => sessions.find((session) => session.id === selectedSessionId) ?? sessions[0],
    [sessions, selectedSessionId],
  )

  const filteredSessions = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return sessions
    return sessions.filter((session) => {
      return (
        session.label.toLowerCase().includes(q)
        || session.id.toLowerCase().includes(q)
        || channelLabel[session.channel].toLowerCase().includes(q)
      )
    })
  }, [query, sessions])

  useEffect(() => {
    const onDocClick = (event: MouseEvent) => {
      if (!desktopRef.current) return
      if (!desktopRef.current.contains(event.target as Node)) {
        setOpenDesktop(false)
      }
    }
    document.addEventListener('mousedown', onDocClick)
    return () => document.removeEventListener('mousedown', onDocClick)
  }, [])

  const closeAll = () => {
    setOpenDesktop(false)
    setOpenMobile(false)
    setQuery('')
  }

  if (sessions.length === 0 || !selectedSession) return null

  const listBody = (
    <PanelCard className='p-2 shadow-[var(--ds-shadow-elevated)]'>
      <div className='mb-2 flex items-center gap-2 rounded-lg border border-[#2a2a2a] bg-[#141414] px-2 py-1.5'>
        <FiSearch className='h-3.5 w-3.5 text-zinc-500' aria-hidden='true' />
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder='Search sessions'
          className='w-full bg-transparent text-xs text-zinc-100 outline-none placeholder:text-zinc-600'
          aria-label='Search sessions'
        />
      </div>
      <div className='max-h-[55vh] space-y-1 overflow-y-auto pr-0.5'>
        {filteredSessions.length > 0 ? (
          filteredSessions.map((session) => (
            <SessionRow
              key={session.id}
              item={session}
              selected={session.id === selectedSession.id}
              onSelect={(sessionId) => {
                onSelect(sessionId)
                closeAll()
              }}
            />
          ))
        ) : (
          <p className='rounded-lg bg-[#141414] px-2.5 py-3 text-xs text-zinc-500'>No matching sessions.</p>
        )}
      </div>
    </PanelCard>
  )

  return (
    <>
      <div ref={desktopRef} className='relative hidden sm:block'>
        <button
          type='button'
          onClick={() => {
            setOpenDesktop((prev) => !prev)
            setOpenMobile(false)
          }}
          className='flex min-w-[220px] max-w-[280px] items-center gap-2 rounded-lg border border-[#2a2a2a] bg-[#171717] px-2.5 py-1.5 text-left hover:border-zinc-600 transition-colors cursor-pointer'
          aria-haspopup='listbox'
          aria-expanded={openDesktop}
          aria-label='Switch session'
        >
          <FiMonitor className='h-3.5 w-3.5 text-zinc-500' aria-hidden='true' />
          <div className='min-w-0 flex-1'>
            <p className='truncate text-xs text-zinc-100'>{selectedSession.label}</p>
            <p className='truncate text-[10px] text-zinc-500'>{selectedSession.id}</p>
          </div>
          <StatusBadge label={channelLabel[selectedSession.channel]} tone={selectedSession.channel === 'chat' ? 'info' : selectedSession.channel === 'browser' ? 'warning' : 'default'} />
          <FiChevronDown className={`h-3.5 w-3.5 text-zinc-500 transition-transform ${openDesktop ? 'rotate-180' : ''}`} aria-hidden='true' />
        </button>

        {openDesktop && <div className='absolute left-0 top-full z-30 mt-2 w-[360px]'>{listBody}</div>}
      </div>

      <div className='sm:hidden'>
        <button
          type='button'
          onClick={() => {
            setOpenMobile(true)
            setOpenDesktop(false)
          }}
          className='flex max-w-[78vw] items-center gap-2 rounded-lg border border-[#2a2a2a] bg-[#171717] px-2.5 py-1.5 text-left hover:border-zinc-600 transition-colors cursor-pointer'
          aria-label='Open session switcher'
        >
          <FiSmartphone className='h-3.5 w-3.5 text-zinc-500' aria-hidden='true' />
          <div className='min-w-0'>
            <p className='truncate text-xs text-zinc-100'>{selectedSession.label}</p>
          </div>
          <FiChevronDown className='h-3.5 w-3.5 text-zinc-500' aria-hidden='true' />
        </button>
      </div>

      {openMobile && (
        <div className='fixed inset-0 z-50 flex flex-col bg-black/70 p-3 backdrop-blur-sm sm:hidden'>
          <div className='mb-2 flex items-center justify-between'>
            <p className='text-sm font-medium text-zinc-100'>Switch session</p>
            <button
              type='button'
              onClick={closeAll}
              className='rounded-md border border-[#2a2a2a] bg-[#151515] p-1.5 text-zinc-300'
              aria-label='Close session switcher'
            >
              <FiX className='h-4 w-4' />
            </button>
          </div>
          {listBody}
        </div>
      )}
    </>
  )
}
