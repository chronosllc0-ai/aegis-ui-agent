import { useEffect, useState } from 'react'

import { apiRequest } from '../../lib/api'
import { HUB_BADGE, type HubSubmission } from './types'

type Props = { isAdmin: boolean }
const RISK_TAGS = ['clean', 'low_risk', 'suspicious', 'malicious', 'scan_pending', 'scan_failed'] as const

export function ReviewQueue({ isAdmin }: Props) {
  const [items, setItems] = useState<HubSubmission[]>([])
  const [state, setState] = useState('')
  const [risk, setRisk] = useState('')

  useEffect(() => {
    if (!isAdmin) return
    const params = new URLSearchParams()
    if (state) params.set('state', state)
    if (risk) params.set('risk_label', risk)
    void apiRequest<{ items: HubSubmission[] }>(`/api/skills/hub/review-queue${params.toString() ? `?${params.toString()}` : ''}`).then((data) => setItems(data.items ?? []))
  }, [isAdmin, state, risk])

  if (!isAdmin) return null

  return (
    <section className='rounded-xl border border-[#2a2a2a] bg-[#121212] p-4'>
      <h3 className='mb-2 text-sm font-semibold'>Skill Hub Review Queue (Admin)</h3>
      <div className='mb-2 flex gap-2'>
        <input className='rounded border border-[#2a2a2a] bg-[#0f0f0f] px-2 py-1 text-xs' placeholder='state' value={state} onChange={(e) => setState(e.target.value)} />
      </div>
      <div className='mb-2 flex flex-wrap gap-2'>
        {RISK_TAGS.map((tag) => (
          <button
            key={tag}
            type='button'
            className={`rounded-full border px-2 py-0.5 text-[10px] ${risk === tag ? 'border-cyan-500/40 bg-cyan-500/10 text-cyan-300' : 'border-[#2a2a2a] text-zinc-400'}`}
            onClick={() => setRisk((prev) => (prev === tag ? '' : tag))}
          >
            {tag}
          </button>
        ))}
      </div>
      <div className='space-y-2'>
        {items.map((item) => (
          <div key={item.id} className='rounded border border-[#2a2a2a] bg-[#171717] p-2 text-xs'>
            <div className='font-medium text-zinc-200'>{item.title}</div>
            <div className='text-zinc-500'>{item.skill_slug}</div>
            <span className={`mt-1 inline-block rounded-full border px-2 py-0.5 text-[10px] ${HUB_BADGE[item.current_state]}`}>{item.current_state}</span>
            <span className='ml-2 mt-1 inline-block rounded-full border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-[10px] text-amber-300'>{item.risk_label}</span>
          </div>
        ))}
      </div>
    </section>
  )
}
