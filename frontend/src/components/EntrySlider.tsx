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
    <section className={`overflow-hidden rounded-2xl border border-[#1f1f1f] bg-[radial-gradient(circle_at_top,rgba(59,130,246,0.2),transparent_35%),linear-gradient(180deg,#131722_0%,#0d1018_100%)] p-4 text-left shadow-[0_20px_80px_rgba(0,0,0,0.35)] sm:rounded-[28px] sm:p-6 ${className}`}>
      <div className='flex items-center justify-between gap-2 sm:gap-3'>
        <div className='inline-flex items-center gap-1.5 rounded-full border border-blue-400/20 bg-blue-400/10 px-2 py-1 text-[10px] uppercase tracking-[0.2em] text-blue-200 sm:gap-2 sm:px-3 sm:text-[11px] sm:tracking-[0.24em]'>
          {active.icon('h-3 w-3 sm:h-3.5 sm:w-3.5')}
          <span>{active.eyebrow}</span>
        </div>
        <div className='rounded-xl border border-white/10 bg-white/5 px-2 py-1.5 text-right sm:rounded-2xl sm:px-3 sm:py-2'>
          <p className='text-[9px] uppercase tracking-[0.16em] text-zinc-400 sm:text-[11px] sm:tracking-[0.18em]'>{active.statLabel}</p>
          <p className='mt-0.5 text-sm font-semibold text-white sm:mt-1 sm:text-lg'>{active.statValue}</p>
        </div>
      </div>

      <div className='mt-5 min-h-[160px] sm:mt-8 sm:min-h-[200px]'>
        <h3 className='max-w-md text-xl font-semibold leading-tight text-white sm:text-2xl md:text-3xl'>{active.title}</h3>
        <p className='mt-3 max-w-lg text-xs leading-5 text-zinc-300 sm:mt-4 sm:text-sm sm:leading-6'>{active.description}</p>
        <div className='mt-4 grid gap-1.5 sm:mt-6 sm:gap-2'>
          {active.bullets.map((bullet) => (
            <div key={bullet} className='rounded-xl border border-white/8 bg-white/4 px-3 py-2 text-xs text-zinc-200 backdrop-blur-sm sm:rounded-2xl sm:px-4 sm:py-3 sm:text-sm'>
              {bullet}
            </div>
          ))}
        </div>
      </div>

      <div className='mt-5 flex items-center justify-between gap-2 sm:mt-8 sm:gap-3'>
        <div className='flex items-center gap-1.5 sm:gap-2'>
          {slides.map((slide, index) => (
            <button
              key={slide.id}
              type='button'
              onClick={() => setActiveIndex(index)}
              aria-label={`Show slide ${index + 1}`}
              className={`h-2 rounded-full transition-all sm:h-2.5 ${index === activeIndex ? 'w-6 bg-blue-400 sm:w-8' : 'w-2 bg-zinc-600 hover:bg-zinc-500 sm:w-2.5'}`}
            />
          ))}
        </div>
        <div className='flex items-center gap-1.5 sm:gap-2'>
          <button
            type='button'
            onClick={() => setActiveIndex((current) => (current - 1 + slides.length) % slides.length)}
            className='rounded-full border border-white/10 bg-white/5 px-2 py-1.5 text-[10px] text-zinc-200 hover:bg-white/10 sm:px-3 sm:py-2 sm:text-xs'
          >
            Prev
          </button>
          <button
            type='button'
            onClick={() => setActiveIndex((current) => (current + 1) % slides.length)}
            className='rounded-full border border-white/10 bg-white/5 px-2 py-1.5 text-[10px] text-zinc-200 hover:bg-white/10 sm:px-3 sm:py-2 sm:text-xs'
          >
            Next
          </button>
        </div>
      </div>
    </section>
  )
}

export type { EntrySlide }
