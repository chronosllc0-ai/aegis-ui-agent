import { useEffect, useRef, useState } from 'react'

type ScreenViewProps = {
  dataTour?: string
  frameSrc: string
  isWorking: boolean
  steeringFlashKey: number
  onExampleClick: (prompt: string) => void
  lastClickCoords?: { x: number; y: number } | null
  handoffActive?: boolean
  onHumanBrowserAction?: (action: { kind: 'click' | 'type_text' | 'scroll' | 'press_key'; x?: number; y?: number; text?: string; key?: string; deltaY?: number }) => void
}

const EXAMPLES = [
  'Go to Google and search for the latest AI news',
  'Open GitHub and star the top trending repo',
  'Navigate to Amazon and find wireless headphones under $50',
  'Go to Wikipedia and summarize the article on quantum computing',
]

export function ScreenView({ frameSrc, isWorking, steeringFlashKey, onExampleClick, dataTour, lastClickCoords, handoffActive = false, onHumanBrowserAction }: ScreenViewProps) {
  const [displayFrame, setDisplayFrame] = useState('')
  const [clickAnim, setClickAnim] = useState<{ x: number; y: number; key: number } | null>(null)
  const containerRef = useRef<HTMLDivElement | null>(null)

  const mapClientToViewport = (clientX: number, clientY: number): { x: number; y: number } | null => {
    const rect = containerRef.current?.getBoundingClientRect()
    if (!rect || rect.width <= 0 || rect.height <= 0) return null
    const relX = Math.min(Math.max(clientX - rect.left, 0), rect.width)
    const relY = Math.min(Math.max(clientY - rect.top, 0), rect.height)
    return {
      x: Math.round((relX / rect.width) * 1280),
      y: Math.round((relY / rect.height) * 720),
    }
  }

  useEffect(() => {
    if (!lastClickCoords) return
    setClickAnim({ ...lastClickCoords, key: Date.now() })
    const t = window.setTimeout(() => setClickAnim(null), 1500)
    return () => window.clearTimeout(t)
  }, [lastClickCoords])

  useEffect(() => {
    if (!frameSrc) return
    if (!displayFrame) {
      const timeout = window.setTimeout(() => setDisplayFrame(frameSrc), 0)
      return () => window.clearTimeout(timeout)
    }
    if (frameSrc !== displayFrame) {
      const timeout = window.setTimeout(() => setDisplayFrame(frameSrc), 0)
      return () => window.clearTimeout(timeout)
    }
  }, [displayFrame, frameSrc])

  const hasFrame = Boolean(displayFrame)

  return (
    <section data-tour={dataTour} className='relative h-full min-h-0 overflow-hidden rounded-2xl border border-[#2a2a2a] bg-[#1a1a1a]'>
      {/* 4-corner activity indicators */}
      {isWorking && (
        <>
          {/* Top-left */}
          <div className='absolute top-0 left-0 z-20 h-8 w-8 pointer-events-none'>
            <div className='absolute top-0 left-0 h-2 w-8 bg-blue-500 animate-pulse rounded-tl-2xl' />
            <div className='absolute top-0 left-0 h-8 w-2 bg-blue-500 animate-pulse rounded-tl-2xl' />
          </div>
          {/* Top-right */}
          <div className='absolute top-0 right-0 z-20 h-8 w-8 pointer-events-none'>
            <div className='absolute top-0 right-0 h-2 w-8 bg-blue-500 animate-pulse rounded-tr-2xl' />
            <div className='absolute top-0 right-0 h-8 w-2 bg-blue-500 animate-pulse rounded-tr-2xl' />
          </div>
          {/* Bottom-left */}
          <div className='absolute bottom-0 left-0 z-20 h-8 w-8 pointer-events-none'>
            <div className='absolute bottom-0 left-0 h-2 w-8 bg-blue-500 animate-pulse rounded-bl-2xl' />
            <div className='absolute bottom-0 left-0 h-8 w-2 bg-blue-500 animate-pulse rounded-bl-2xl' />
          </div>
          {/* Bottom-right */}
          <div className='absolute bottom-0 right-0 z-20 h-8 w-8 pointer-events-none'>
            <div className='absolute bottom-0 right-0 h-2 w-8 bg-blue-500 animate-pulse rounded-br-2xl' />
            <div className='absolute bottom-0 right-0 h-8 w-2 bg-blue-500 animate-pulse rounded-br-2xl' />
          </div>
        </>
      )}
      {steeringFlashKey > 0 && (
        <div
          key={steeringFlashKey}
          className='absolute left-4 top-4 z-20 animate-[fade-slide_900ms_ease-out] rounded-md border border-blue-400/60 bg-blue-500/20 px-3 py-1 text-sm text-blue-200'
        >
          Steering...
        </div>
      )}
      {hasFrame ? (
        <>
          <div
            ref={containerRef}
            className={`absolute inset-0 ${handoffActive ? 'cursor-crosshair' : ''}`}
            tabIndex={handoffActive ? 0 : -1}
            onClick={(event) => {
              if (!handoffActive || !onHumanBrowserAction) return
              const mapped = mapClientToViewport(event.clientX, event.clientY)
              if (!mapped) return
              onHumanBrowserAction({ kind: 'click', x: mapped.x, y: mapped.y })
            }}
            onWheel={(event) => {
              if (!handoffActive || !onHumanBrowserAction) return
              onHumanBrowserAction({ kind: 'scroll', deltaY: Math.round(event.deltaY) })
            }}
            onKeyDown={(event) => {
              if (!handoffActive || !onHumanBrowserAction) return
              if (event.key.length === 1) {
                onHumanBrowserAction({ kind: 'type_text', text: event.key })
                return
              }
              onHumanBrowserAction({ kind: 'press_key', key: event.key })
            }}
          >
            <img src={displayFrame} alt='Live browser stream' className='absolute inset-0 h-full w-full object-cover' />
          </div>
          {handoffActive && (
            <div className='absolute inset-x-3 top-3 z-20 rounded-lg border border-amber-500/50 bg-amber-500/15 px-3 py-2 text-xs text-amber-200'>
              Manual handoff active: you can click, type, scroll, and press keys in the browser pane.
            </div>
          )}
          {clickAnim && (
            <div
              key={clickAnim.key}
              className='absolute z-30 pointer-events-none'
              style={{
                left: `${(clickAnim.x / 1280) * 100}%`,
                top: `${(clickAnim.y / 720) * 100}%`,
                transform: 'translate(-50%, -50%)',
              }}
            >
              <div className='h-6 w-6 animate-ping rounded-full border-2 border-blue-400 bg-blue-400/20' />
            </div>
          )}
        </>
      ) : (
        <div className='flex min-h-full w-full flex-col items-center justify-start px-3 py-5 text-center sm:px-6 sm:py-8 md:justify-center'>
          <img src='/aegis-shield.png' alt='Aegis logo' className='mb-3 h-10 w-10 sm:mb-5 sm:h-16 sm:w-16 object-contain mix-blend-screen' />
          <h2 className='text-xl font-semibold sm:text-2xl md:text-3xl'>Tell me what to do</h2>
          <p className='mb-4 mt-1.5 max-w-xl text-xs text-zinc-400 sm:mb-8 sm:mt-2 sm:text-sm'>Aegis can operate any UI with visual understanding. Start with a natural language instruction or choose an example below.</p>
          <div className='grid w-full max-w-3xl gap-2 sm:gap-3 sm:grid-cols-2'>
            {EXAMPLES.map((prompt) => (
              <button key={prompt} type='button' onClick={() => onExampleClick(prompt)} className='w-full overflow-hidden rounded-lg border border-[#2a2a2a] bg-[#111] p-2 text-left text-xs text-zinc-200 transition hover:border-blue-500/60 hover:bg-zinc-900 sm:rounded-xl sm:p-3 sm:text-sm'>
                <span className='line-clamp-2 break-words'>{prompt}</span>
              </button>
            ))}
          </div>
          <p className='mt-3 text-[10px] text-zinc-500 sm:mt-5 sm:text-xs'>Waiting for first live frame...</p>
        </div>
      )}
    </section>
  )
}
