import { useEffect, useState, type ReactElement } from 'react'

type EntrySlide = {
  id: string
  eyebrow: string
  title: string
  description: string
  bullets: string[]
  statLabel: string
  statValue: string
  icon: (className?: string) => ReactElement
}

type EntrySliderProps = {
  slides: EntrySlide[]
  className?: string
}

export function EntrySlider({ slides, className = '' }: EntrySliderProps) {
  const [activeIndex, setActiveIndex] = useState(0)

  useEffect(() => {
    if (slides.length <= 1) return
    const intervalId = window.setInterval(() => {
      setActiveIndex((current) => (current + 1) % slides.length)
    }, 4500)
    return () => window.clearInterval(intervalId)
  }, [slides.length])

  if (!slides.length) return null

  const active = slides[activeIndex]

  return (
    <section className={`overflow-hidden rounded-[28px] border border-[#1f1f1f] bg-[radial-gradient(circle_at_top,rgba(59,130,246,0.2),transparent_35%),linear-gradient(180deg,#131722_0%,#0d1018_100%)] p-6 text-left shadow-[0_20px_80px_rgba(0,0,0,0.35)] ${className}`}>
      <div className='flex items-center justify-between gap-3'>
        <div className='inline-flex items-center gap-2 rounded-full border border-blue-400/20 bg-blue-400/10 px-3 py-1 text-[11px] uppercase tracking-[0.24em] text-blue-200'>
          {active.icon('h-3.5 w-3.5')}
          <span>{active.eyebrow}</span>
        </div>
        <div className='rounded-2xl border border-white/10 bg-white/5 px-3 py-2 text-right'>
          <p className='text-[11px] uppercase tracking-[0.18em] text-zinc-400'>{active.statLabel}</p>
          <p className='mt-1 text-lg font-semibold text-white'>{active.statValue}</p>
        </div>
      </div>

      <div className='mt-8 min-h-[200px]'>
        <h3 className='max-w-md text-3xl font-semibold leading-tight text-white'>{active.title}</h3>
        <p className='mt-4 max-w-lg text-sm leading-6 text-zinc-300'>{active.description}</p>
        <div className='mt-6 grid gap-2'>
          {active.bullets.map((bullet) => (
            <div key={bullet} className='rounded-2xl border border-white/8 bg-white/4 px-4 py-3 text-sm text-zinc-200 backdrop-blur-sm'>
              {bullet}
            </div>
          ))}
        </div>
      </div>

      <div className='mt-8 flex items-center justify-between gap-3'>
        <div className='flex items-center gap-2'>
          {slides.map((slide, index) => (
            <button
              key={slide.id}
              type='button'
              onClick={() => setActiveIndex(index)}
              aria-label={`Show slide ${index + 1}`}
              className={`h-2.5 rounded-full transition-all ${index === activeIndex ? 'w-8 bg-blue-400' : 'w-2.5 bg-zinc-600 hover:bg-zinc-500'}`}
            />
          ))}
        </div>
        <div className='flex items-center gap-2'>
          <button
            type='button'
            onClick={() => setActiveIndex((current) => (current - 1 + slides.length) % slides.length)}
            className='rounded-full border border-white/10 bg-white/5 px-3 py-2 text-xs text-zinc-200 hover:bg-white/10'
          >
            Prev
          </button>
          <button
            type='button'
            onClick={() => setActiveIndex((current) => (current + 1) % slides.length)}
            className='rounded-full border border-white/10 bg-white/5 px-3 py-2 text-xs text-zinc-200 hover:bg-white/10'
          >
            Next
          </button>
        </div>
      </div>
    </section>
  )
}

export type { EntrySlide }
