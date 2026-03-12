import { useEffect, useState } from 'react'

type ScreenViewProps = {
  frameSrc: string
  isWorking: boolean
  steeringFlashKey: number
  onExampleClick: (prompt: string) => void
}

const EXAMPLES = [
  'Go to Google and search for the latest AI news',
  'Open GitHub and star the top trending repo',
  'Navigate to Amazon and find wireless headphones under $50',
  'Go to Wikipedia and summarize the article on quantum computing',
]

export function ScreenView({ frameSrc, isWorking, steeringFlashKey, onExampleClick }: ScreenViewProps) {
  const [showSteering, setShowSteering] = useState<boolean>(false)
  const [displayFrame, setDisplayFrame] = useState<string>('')
  const [overlayFrame, setOverlayFrame] = useState<string>('')
  const [fading, setFading] = useState<boolean>(false)

  useEffect(() => {
    if (!frameSrc) return
    if (!displayFrame) {
      setDisplayFrame(frameSrc)
      return
    }
    if (frameSrc !== displayFrame) {
      setOverlayFrame(frameSrc)
      setFading(true)
      const timeout = window.setTimeout(() => {
        setDisplayFrame(frameSrc)
        setOverlayFrame('')
        setFading(false)
      }, 250)
      return () => window.clearTimeout(timeout)
    }
  }, [displayFrame, frameSrc])

  useEffect(() => {
    if (steeringFlashKey === 0) {
      return
    }
    setShowSteering(true)
    const timeout = window.setTimeout(() => setShowSteering(false), 900)
    return () => window.clearTimeout(timeout)
  }, [steeringFlashKey])

  const hasFrame = Boolean(displayFrame)

  return (
    <section className='relative h-full min-h-[420px] overflow-hidden rounded-xl border border-[#2a2a2a] bg-[#1a1a1a]'>
      <div className='absolute inset-x-0 top-0 z-20 h-0.5 bg-zinc-800'>
        <div className={`h-full bg-blue-500 transition-all ${isWorking ? 'w-full animate-pulse' : 'w-0'}`} />
      </div>
      {showSteering && (
        <div className='absolute left-4 top-4 z-20 rounded-md border border-blue-400/60 bg-blue-500/20 px-3 py-1 text-sm text-blue-200'>
          Steering...
        </div>
      )}
      {hasFrame ? (
        <>
          <img src={displayFrame} alt='Live browser stream' className='absolute inset-0 h-full w-full object-contain' />
          {overlayFrame && (
            <img
              src={overlayFrame}
              alt='Incoming browser stream'
              className={`absolute inset-0 h-full w-full object-contain transition-opacity duration-300 ${fading ? 'opacity-100' : 'opacity-0'}`}
            />
          )}
        </>
      ) : (
        <div className='flex h-full flex-col items-center justify-center px-6 text-center'>
          <div className='mb-4 text-6xl'>🛡️</div>
          <h2 className='text-2xl font-semibold'>Tell me what to do</h2>
          <p className='mb-6 mt-2 text-sm text-zinc-400'>Aegis can operate any UI with visual understanding.</p>
          <div className='grid w-full max-w-3xl gap-3 md:grid-cols-2'>
            {EXAMPLES.map((prompt) => (
              <button
                key={prompt}
                type='button'
                onClick={() => onExampleClick(prompt)}
                className='rounded-xl border border-[#2a2a2a] bg-[#111] p-3 text-left text-sm text-zinc-200 transition hover:border-blue-500/60 hover:bg-zinc-900'
              >
                {prompt}
              </button>
            ))}
          </div>
        </div>
      )}
    </section>
  )
}
