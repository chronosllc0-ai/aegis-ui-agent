import { useCallback, useEffect, useRef, useState, useSyncExternalStore, type CSSProperties, type ReactNode } from 'react'

type RevealProps = {
  children: ReactNode
  className?: string
  delayMs?: number
  durationMs?: number
  distance?: number
  mode?: 'scroll' | 'load'
}

/* Detect prefers-reduced-motion via useSyncExternalStore (no setState in effect) */
function getReducedMotionSnapshot(): boolean {
  return typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
}
function subscribeReducedMotion(cb: () => void): () => void {
  if (typeof window === 'undefined') return () => {}
  const mq = window.matchMedia('(prefers-reduced-motion: reduce)')
  mq.addEventListener('change', cb)
  return () => mq.removeEventListener('change', cb)
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
  const reducedMotion = useSyncExternalStore(subscribeReducedMotion, getReducedMotionSnapshot, () => false)
  const [visible, setVisible] = useState(reducedMotion)

  const reveal = useCallback(() => setVisible(true), [])

  useEffect(() => {
    if (reducedMotion || visible) return

    if (mode === 'load') {
      const frameId = window.requestAnimationFrame(reveal)
      return () => window.cancelAnimationFrame(frameId)
    }

    const node = ref.current
    if (!node) return

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          reveal()
          observer.disconnect()
        }
      },
      { threshold: 0.18, rootMargin: '0px 0px -10% 0px' },
    )

    observer.observe(node)
    return () => observer.disconnect()
  }, [mode, reducedMotion, visible, reveal])

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
