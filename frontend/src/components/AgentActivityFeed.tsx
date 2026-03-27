import { useCallback, useEffect, useRef, useState } from 'react'

type FeedEvent = {
  type: string
  step_id?: string
  title?: string
  provider?: string
  model?: string
  result_preview?: string
  tokens_used?: number
  error?: string
  reason?: string
  status?: string
  total_steps?: number
  timestamp: number
}

type AgentActivityFeedProps = {
  planId: string
  wsBaseUrl?: string
}

const EVENT_ICONS: Record<string, { icon: string; color: string }> = {
  plan_started: { icon: '▶', color: 'text-blue-400' },
  step_started: { icon: '◉', color: 'text-blue-400' },
  step_completed: { icon: '✓', color: 'text-emerald-400' },
  step_failed: { icon: '✗', color: 'text-red-400' },
  step_skipped: { icon: '—', color: 'text-zinc-500' },
  plan_completed: { icon: '■', color: 'text-emerald-400' },
  plan_cancelled: { icon: '■', color: 'text-amber-400' },
  heartbeat: { icon: '·', color: 'text-zinc-700' },
}

export function AgentActivityFeed({ planId, wsBaseUrl }: AgentActivityFeedProps) {
  const [events, setEvents] = useState<FeedEvent[]>([])
  const [connected, setConnected] = useState(false)
  const feedRef = useRef<HTMLDivElement>(null)
  const wsRef = useRef<WebSocket | null>(null)

  const addEvent = useCallback((evt: FeedEvent) => {
    if (evt.type === 'heartbeat') return
    setEvents((prev) => [...prev, evt])
  }, [])

  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const base = wsBaseUrl || `${protocol}//${window.location.host}`
    const ws = new WebSocket(`${base}/ws/plan/${planId}`)
    wsRef.current = ws

    ws.onopen = () => setConnected(true)
    ws.onclose = () => setConnected(false)
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        addEvent({ ...data, timestamp: Date.now() })
      } catch {
        // ignore parse errors
      }
    }

    return () => {
      ws.close()
      wsRef.current = null
    }
  }, [planId, wsBaseUrl, addEvent])

  useEffect(() => {
    if (feedRef.current) {
      feedRef.current.scrollTop = feedRef.current.scrollHeight
    }
  }, [events])

  return (
    <div className='rounded-xl border border-[#2a2a2a] bg-[#1a1a1a]'>
      <div className='flex items-center justify-between border-b border-[#2a2a2a] px-4 py-2.5'>
        <h4 className='text-xs font-semibold uppercase tracking-wider text-zinc-400'>Agent Activity</h4>
        <div className='flex items-center gap-1.5'>
          <span className={`h-2 w-2 rounded-full ${connected ? 'bg-emerald-400' : 'bg-zinc-600'}`} />
          <span className='text-[10px] text-zinc-500'>{connected ? 'Live' : 'Disconnected'}</span>
        </div>
      </div>

      <div ref={feedRef} className='max-h-[400px] overflow-y-auto p-3'>
        {events.length === 0 ? (
          <p className='py-4 text-center text-xs text-zinc-600'>Waiting for events...</p>
        ) : (
          <div className='space-y-1'>
            {events.map((event, idx) => {
              const style = EVENT_ICONS[event.type] || EVENT_ICONS.heartbeat
              return (
                <div key={`${event.type}-${event.step_id || ''}-${idx}`} className='flex items-start gap-2 rounded-lg px-2 py-1.5 hover:bg-zinc-800/50'>
                  <span className={`mt-0.5 text-xs font-mono ${style.color}`}>{style.icon}</span>
                  <div className='min-w-0 flex-1'>
                    <span className='text-xs text-zinc-300'>
                      {event.title || event.type.replace(/_/g, ' ')}
                    </span>
                    {event.provider && (
                      <span className='ml-2 rounded bg-zinc-700 px-1 py-0.5 text-[9px] text-zinc-500'>
                        {event.provider}{event.model ? `/${event.model}` : ''}
                      </span>
                    )}
                    {event.result_preview && (
                      <p className='mt-0.5 line-clamp-2 text-[11px] text-zinc-500'>{event.result_preview}</p>
                    )}
                    {event.error && (
                      <p className='mt-0.5 text-[11px] text-red-400'>{event.error}</p>
                    )}
                    {event.tokens_used ? (
                      <span className='text-[9px] text-zinc-600'>{event.tokens_used.toLocaleString()} tokens</span>
                    ) : null}
                  </div>
                  <span className='shrink-0 text-[9px] text-zinc-700'>
                    {new Date(event.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                  </span>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
