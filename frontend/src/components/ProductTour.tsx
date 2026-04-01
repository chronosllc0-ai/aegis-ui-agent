import { useCallback, useEffect, useRef, useState } from 'react'

/* ── storage key ─────────────────────────────────────────────────── */
const TOUR_KEY = 'aegis.tour.complete'
export const isTourComplete = () => localStorage.getItem(TOUR_KEY) === '1'
export const markTourComplete = () => localStorage.setItem(TOUR_KEY, '1')

/* ── tour step definitions ─────────────────────────────────────────── */
type TourStep = {
  /** CSS selector for the element to highlight */
  selector: string
  /** Fallback: if selector not found, try this */
  fallbackSelector?: string
  title: string
  body: string
  placement: 'top' | 'bottom' | 'left' | 'right'
}

const STEPS: TourStep[] = [
  {
    selector: '[data-tour="screen-view"]',
    fallbackSelector: '.grid > div:first-child',
    title: 'Live screen view',
    body: 'This is where you see the browser in real time. Aegis watches and controls the page while you stay in the loop.',
    placement: 'right',
  },
  {
    selector: '[data-tour="action-log"]',
    fallbackSelector: '.grid > div:last-child',
    title: 'Action log',
    body: 'Every action Aegis takes appears here - clicks, navigations, form fills. You can review everything as it happens.',
    placement: 'left',
  },
  {
    selector: '[data-tour="input-bar"]',
    title: 'Instruction bar',
    body: 'Type what you want Aegis to do. You can steer, interrupt, or queue follow-up tasks while the agent is running.',
    placement: 'top',
  },
  {
    selector: '[data-tour="sidebar"]',
    fallbackSelector: 'aside',
    title: 'Sidebar',
    body: 'Your task history, workflow templates, usage stats, and settings all live here. Start a new task anytime.',
    placement: 'right',
  },
  {
    selector: '[data-tour="model-picker"]',
    title: 'Model picker',
    body: 'Switch AI providers and models on the fly - Google, OpenAI, Anthropic, Mistral, or Groq. Pick the best tool for the job.',
    placement: 'top',
  },
]

type TourProps = {
  onComplete: () => void
}

/* ── tooltip position calculator ──────────────────────────────────── */
function computeTooltipPos(rect: DOMRect, placement: TourStep['placement']) {
  const gap = 12
  const tooltipW = 320
  const tooltipH = 160 // estimate

  let top = 0
  let left = 0

  switch (placement) {
    case 'bottom':
      top = rect.bottom + gap
      left = rect.left + rect.width / 2 - tooltipW / 2
      break
    case 'top':
      top = rect.top - tooltipH - gap
      left = rect.left + rect.width / 2 - tooltipW / 2
      break
    case 'right':
      top = rect.top + rect.height / 2 - tooltipH / 2
      left = rect.right + gap
      break
    case 'left':
      top = rect.top + rect.height / 2 - tooltipH / 2
      left = rect.left - tooltipW - gap
      break
  }

  // clamp to viewport
  top = Math.max(8, Math.min(top, window.innerHeight - tooltipH - 8))
  left = Math.max(8, Math.min(left, window.innerWidth - tooltipW - 8))

  return { top, left, width: tooltipW }
}

/* ── main tour component ──────────────────────────────────────────── */
export function ProductTour({ onComplete }: TourProps) {
  const [current, setCurrent] = useState(0)
  const [targetRect, setTargetRect] = useState<DOMRect | null>(null)
  const tooltipRef = useRef<HTMLDivElement>(null)
  const step = STEPS[current]

  const findTarget = useCallback(() => {
    if (!step) return null
    let el = document.querySelector(step.selector)
    if (!el && step.fallbackSelector) el = document.querySelector(step.fallbackSelector)
    return el
  }, [step])

  // position the highlight and tooltip
  useEffect(() => {
    const update = () => {
      const el = findTarget()
      if (el) {
        setTargetRect(el.getBoundingClientRect())
      } else {
        setTargetRect(null)
      }
    }
    update()
    // re-measure on resize/scroll
    window.addEventListener('resize', update)
    window.addEventListener('scroll', update, true)
    const timer = setInterval(update, 500) // fallback poll
    return () => {
      window.removeEventListener('resize', update)
      window.removeEventListener('scroll', update, true)
      clearInterval(timer)
    }
  }, [current, findTarget])

  const nextStep = () => {
    if (current < STEPS.length - 1) {
      setCurrent((c) => c + 1)
    } else {
      markTourComplete()
      onComplete()
    }
  }

  const skip = () => {
    markTourComplete()
    onComplete()
  }

  if (!step) return null

  const pos = targetRect ? computeTooltipPos(targetRect, step.placement) : null
  const pad = 6

  return (
    <div className='fixed inset-0 z-[60]'>
      {/* overlay with cutout */}
      <svg className='absolute inset-0 h-full w-full' style={{ pointerEvents: 'none' }}>
        <defs>
          <mask id='tour-mask'>
            <rect width='100%' height='100%' fill='white' />
            {targetRect && (
              <rect
                x={targetRect.left - pad}
                y={targetRect.top - pad}
                width={targetRect.width + pad * 2}
                height={targetRect.height + pad * 2}
                rx='12'
                fill='black'
              />
            )}
          </mask>
        </defs>
        <rect width='100%' height='100%' fill='rgba(0,0,0,0.65)' mask='url(#tour-mask)' style={{ pointerEvents: 'auto' }} />
      </svg>

      {/* highlight border */}
      {targetRect && (
        <div
          className='pointer-events-none absolute rounded-xl border-2 border-cyan-400/60 shadow-[0_0_24px_rgba(34,211,238,0.15)]'
          style={{
            top: targetRect.top - pad,
            left: targetRect.left - pad,
            width: targetRect.width + pad * 2,
            height: targetRect.height + pad * 2,
            transition: 'all 0.35s cubic-bezier(.4,0,.2,1)',
          }}
        />
      )}

      {/* tooltip */}
      {pos && (
        <div
          ref={tooltipRef}
          className='absolute z-10 rounded-2xl border border-white/10 bg-[#161b26] p-4 shadow-2xl animate-in fade-in slide-in-from-bottom-1 duration-200'
          style={{ top: pos.top, left: pos.left, width: pos.width }}
        >
          <div className='mb-1 flex items-center justify-between'>
            <h3 className='text-sm font-semibold text-white'>{step.title}</h3>
            <span className='text-xs text-zinc-500'>{current + 1}/{STEPS.length}</span>
          </div>
          <p className='text-xs leading-relaxed text-zinc-400'>{step.body}</p>
          <div className='mt-3 flex items-center justify-between'>
            <button type='button' onClick={skip} className='text-xs text-zinc-500 transition hover:text-zinc-300'>
              Skip tour
            </button>
            <button type='button' onClick={nextStep} className='rounded-lg bg-cyan-500 px-4 py-1.5 text-xs font-semibold text-slate-950 transition hover:bg-cyan-400'>
              {current < STEPS.length - 1 ? 'Next' : 'Done'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
