import type { HubSubmission } from './types'
import { HUB_BADGE } from './types'

type Props = {
  submission: HubSubmission
  allowedTransitions: string[]
  onTransition: (nextState: string) => void
}

export function SubmissionStatusTimeline({ submission, allowedTransitions, onTransition }: Props) {
  return (
    <div className='space-y-2 rounded border border-[#2a2a2a] bg-[#101010] p-3'>
      <div className='flex items-center gap-2'>
        <span className={`rounded-full border px-2 py-0.5 text-[11px] ${HUB_BADGE[submission.current_state]}`}>{submission.current_state}</span>
        <span className='text-[11px] text-zinc-500'>rev {submission.revision}</span>
      </div>
      <div className='space-y-1'>
        {submission.history.map((item) => (
          <div key={item.id} className='rounded border border-[#222] bg-[#151515] p-2 text-[11px]'>
            <div className='text-zinc-300'>{item.from_state} → {item.to_state}</div>
            {item.notes ? <div className='text-zinc-400'>{item.notes}</div> : null}
          </div>
        ))}
      </div>
      {submission.reviewer_notes.length > 0 ? (
        <div className='space-y-1 text-[11px] text-zinc-300'>
          {submission.reviewer_notes.map((note, idx) => <div key={`${submission.id}-note-${idx}`}>• {note}</div>)}
        </div>
      ) : null}
      <div className='flex flex-wrap gap-1'>
        {['submitted', 'under_review', 'changes_requested', 'approved', 'published', 'suspended', 'archived', 'rejected'].map((state) => (
          <button key={state} type='button' disabled={!allowedTransitions.includes(state)} onClick={() => onTransition(state)} className='rounded border border-[#2a2a2a] px-2 py-1 text-[10px] disabled:opacity-30'>
            {state}
          </button>
        ))}
      </div>
    </div>
  )
}
