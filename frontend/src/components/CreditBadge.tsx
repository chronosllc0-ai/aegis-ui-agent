import { useState } from 'react'
import { LuChevronDown, LuChevronUp, LuZap } from 'react-icons/lu'

type CreditBadgeProps = {
  creditsUsed: number
  provider?: string
  model?: string
  inputTokens?: number
  outputTokens?: number
}

export function CreditBadge({ creditsUsed, provider, model, inputTokens, outputTokens }: CreditBadgeProps) {
  const [expanded, setExpanded] = useState(false)
  const hasDetails = provider && model && inputTokens !== undefined && outputTokens !== undefined

  return (
    <span className='inline-flex flex-col'>
      <button
        type='button'
        onClick={() => hasDetails && setExpanded((p) => !p)}
        className={`inline-flex items-center gap-1 rounded-full border border-[#2a2a2a] bg-[#171717] px-2 py-0.5 text-[11px] text-zinc-400 transition ${hasDetails ? 'cursor-pointer hover:border-blue-500/40 hover:text-zinc-300' : 'cursor-default'}`}
        aria-expanded={expanded}
        aria-label={`${creditsUsed} credits used`}
      >
        <LuZap className='h-3 w-3 text-blue-400' aria-hidden='true' />
        <span>{creditsUsed} credit{creditsUsed !== 1 ? 's' : ''}</span>
        {hasDetails && (
          expanded
            ? <LuChevronUp className='h-2.5 w-2.5' aria-hidden='true' />
            : <LuChevronDown className='h-2.5 w-2.5' aria-hidden='true' />
        )}
      </button>
      {expanded && hasDetails && (
        <span className='mt-1 rounded-lg border border-[#2a2a2a] bg-[#111] px-2.5 py-1.5 text-[11px] text-zinc-400'>
          <span className='block'>Provider: <span className='text-zinc-200'>{provider}</span></span>
          <span className='block'>Model: <span className='text-zinc-200'>{model}</span></span>
          <span className='block'>Input: <span className='text-zinc-200'>{inputTokens?.toLocaleString()} tokens</span></span>
          <span className='block'>Output: <span className='text-zinc-200'>{outputTokens?.toLocaleString()} tokens</span></span>
          <span className='block mt-0.5 border-t border-[#2a2a2a] pt-0.5'>Total: <span className='text-blue-300 font-medium'>{creditsUsed} credits</span></span>
        </span>
      )}
    </span>
  )
}
