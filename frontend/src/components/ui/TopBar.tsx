import { type ReactNode, useState } from 'react'

export type TopBarProps = {
  title: string
  status?: ReactNode
  helperText?: ReactNode
  actions?: ReactNode
  helperDefaultOpen?: boolean
  className?: string
}

export function TopBar({
  title,
  status,
  helperText,
  actions,
  helperDefaultOpen = false,
  className = '',
}: TopBarProps) {
  const [mobileActionsOpen, setMobileActionsOpen] = useState(false)
  const [helperOpen, setHelperOpen] = useState(helperDefaultOpen)

  return (
    <header className={`sticky top-1 z-20 rounded-2xl border border-[var(--ds-border-subtle)] bg-[var(--ds-surface-1)]/95 px-3 py-2 backdrop-blur ${className}`}>
      <div className='flex min-h-10 items-center gap-2'>
        <div className='min-w-0 flex-1'>
          <div className='flex min-w-0 items-center gap-2'>
            <h2 className='truncate text-sm font-semibold text-white sm:text-base'>{title}</h2>
            {status && <div className='hidden shrink-0 sm:block'>{status}</div>}
          </div>
          {status && <div className='mt-1 sm:hidden'>{status}</div>}
        </div>

        {actions && (
          <>
            <div className='hidden items-center gap-2 md:flex'>{actions}</div>
            <div className='relative md:hidden'>
              <button
                type='button'
                aria-label='Open header actions'
                aria-expanded={mobileActionsOpen}
                onClick={() => setMobileActionsOpen((prev) => !prev)}
                className='inline-flex min-h-10 min-w-10 items-center justify-center rounded-lg border border-[var(--ds-border-subtle)] bg-[var(--ds-surface-2)] text-[var(--ds-text-secondary)]'
              >
                <span className='text-lg leading-none'>⋮</span>
              </button>
              {mobileActionsOpen && (
                <div className='absolute right-0 z-30 mt-2 w-[min(86vw,18rem)] rounded-xl border border-[var(--ds-border-subtle)] bg-[var(--ds-surface-1)] p-2 shadow-[var(--ds-shadow-soft)]'>
                  <div className='flex flex-col gap-2'>{actions}</div>
                </div>
              )}
            </div>
          </>
        )}
      </div>

      {helperText && (
        <div className='mt-2 border-t border-[var(--ds-border-subtle)] pt-2'>
          <button
            type='button'
            onClick={() => setHelperOpen((prev) => !prev)}
            className='inline-flex min-h-9 items-center gap-1 text-xs text-[var(--ds-text-muted)] hover:text-[var(--ds-text-secondary)]'
            aria-expanded={helperOpen}
          >
            <span>{helperOpen ? 'Hide details' : 'Show details'}</span>
          </button>
          {helperOpen && <div className='pt-1 text-xs text-[var(--ds-text-muted)]'>{helperText}</div>}
        </div>
      )}
    </header>
  )
}
