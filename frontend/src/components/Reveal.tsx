import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react'

type RevealProps = {
  children: ReactNode
  className?: string
  delayMs?: number
  durationMs?: number
  distance?: number
  mode?: 'scroll' | 'load'
}

export function Reveal({
  children,
  className = '',
  delayMs = 0,
  durationMs = 700,
  distance = 28,
  mode = 'scroll',
}: RevealProps) {
  const ref = useRef<HTMLDivElement | null>(null)
  const [visible, setVisible] = useState(mode === 'load' ? false : false)
  const [reducedMotion, setReducedMotion] = useState(false)

  useEffect(() => {
    if (typeof window === 'undefined') return
    const media = window.matchMedia('(prefers-reduced-motion: reduce)')
    const update = () => setReducedMotion(media.matches)
    update()
    media.addEventListener('change', update)
    return () => media.removeEventListener('change', update)
  }, [])

  useEffect(() => {
    if (reducedMotion) {
      setVisible(true)
      return
    }

    if (mode === 'load') {
      const frameId = window.requestAnimationFrame(() => setVisible(true))
      return () => window.cancelAnimationFrame(frameId)
    }

    const node = ref.current
    if (!node) return

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setVisible(true)
          observer.disconnect()
        }
      },
      { threshold: 0.18, rootMargin: '0px 0px -10% 0px' },
    )

    observer.observe(node)
    return () => observer.disconnect()
  }, [mode, reducedMotion])

  const style: CSSProperties | undefined = reducedMotion
    ? undefined
    : {
        opacity: visible ? 1 : 0,
        transform: visible ? 'translate3d(0, 0, 0)' : `translate3d(0, ${distance}px, 0)`,
        transitionProperty: 'opacity, transform',
        transitionDuration: `${durationMs}ms`,
        transitionTimingFunction: 'cubic-bezier(0.22, 1, 0.36, 1)',
        transitionDelay: `${delayMs}ms`,
        willChange: 'opacity, transform',
      }

  return (
    <div ref={ref} className={className} style={style}>
      {children}
    </div>
  )
}
