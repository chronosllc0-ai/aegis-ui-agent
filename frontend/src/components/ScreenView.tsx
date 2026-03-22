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
  const [displayFrame, setDisplayFrame] = useState('')

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
    <section className='relative min-h-[280px] overflow-auto rounded-2xl border border-[#2a2a2a] bg-[#1a1a1a] xl:h-full xl:min-h-0'>
      <div className='absolute inset-x-0 top-0 z-20 h-0.5 bg-zinc-800'>
        <div className={`h-full bg-blue-500 transition-all ${isWorking ? 'w-full animate-pulse' : 'w-0'}`} />
      </div>
      {steeringFlashKey > 0 && (
        <div
          key={steeringFlashKey}
          className='absolute left-4 top-4 z-20 animate-[fade-slide_900ms_ease-out] rounded-md border border-blue-400/60 bg-blue-500/20 px-3 py-1 text-sm text-blue-200'
        >
          Steering...
        </div>
      )}
      {hasFrame ? (
        <img src={displayFrame} alt='Live browser stream' className='absolute inset-0 h-full w-full object-contain' />
      ) : (
        <div className='flex flex-col items-center justify-start px-3 py-5 text-center sm:px-6 sm:py-8 md:justify-center xl:min-h-full'>
          <img src='/shield.svg' alt='Aegis logo' className='mb-3 h-10 w-10 opacity-90 sm:mb-5 sm:h-16 sm:w-16' />
          <h2 className='text-xl font-semibold sm:text-2xl md:text-3xl'>Tell me what to do</h2>
          <p className='mb-4 mt-1.5 max-w-xl text-xs text-zinc-400 sm:mb-8 sm:mt-2 sm:text-sm'>Aegis can operate any UI with visual understanding. Start with a natural language instruction or choose an example below.</p>
          <div className='grid w-full max-w-3xl gap-2 sm:gap-3 sm:grid-cols-2'>
            {EXAMPLES.map((prompt) => (
              <button key={prompt} type='button' onClick={() => onExampleClick(prompt)} className='rounded-lg border border-[#2a2a2a] bg-[#111] p-2 text-left text-xs text-zinc-200 transition hover:border-blue-500/60 hover:bg-zinc-900 sm:rounded-xl sm:p-3 sm:text-sm'>
                {prompt}
              </button>
            ))}
          </div>
          <p className='mt-3 text-[10px] text-zinc-500 sm:mt-5 sm:text-xs'>Waiting for first live frame...</p>
        </div>
      )}
    </section>
  )
}
