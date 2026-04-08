import { useState } from 'react'

import { apiRequest } from '../../lib/api'
import type { HubSubmission } from './types'

type Props = {
  skillId: string
  slug: string
  title: string
  onCreated: (submission: HubSubmission) => void
}

export function SubmissionForm({ skillId, slug, title, onCreated }: Props) {
  const [description, setDescription] = useState('')
  const [risk, setRisk] = useState('unknown')
  const [submitNow, setSubmitNow] = useState(true)
  const [busy, setBusy] = useState(false)

  const handleSubmit = async () => {
    setBusy(true)
    try {
      const data = await apiRequest<{ submission: HubSubmission }>('/api/skills/hub/submissions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          skill_id: skillId,
          skill_slug: slug,
          title,
          description,
          risk_label: risk,
          submit_now: submitNow,
        }),
      })
      onCreated(data.submission)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className='space-y-2 rounded border border-[#2a2a2a] bg-[#111] p-3'>
      <textarea className='h-20 w-full rounded border border-[#2a2a2a] bg-[#0c0c0c] p-2 text-xs' placeholder='Submission notes / summary' value={description} onChange={(e) => setDescription(e.target.value)} />
      <div className='flex items-center gap-2'>
        <select value={risk} onChange={(e) => setRisk(e.target.value)} className='rounded border border-[#2a2a2a] bg-[#0c0c0c] px-2 py-1 text-xs'>
          <option value='unknown'>unknown</option>
          <option value='low'>low</option>
          <option value='medium'>medium</option>
          <option value='high'>high</option>
        </select>
        <label className='flex items-center gap-1 text-xs text-zinc-300'>
          <input type='checkbox' checked={submitNow} onChange={(e) => setSubmitNow(e.target.checked)} />
          Submit now
        </label>
        <button type='button' disabled={busy} onClick={() => void handleSubmit()} className='rounded border border-cyan-500/40 px-2 py-1 text-xs text-cyan-300 disabled:opacity-60'>
          {busy ? 'Submitting…' : 'Create Submission'}
        </button>
      </div>
    </div>
  )
}
