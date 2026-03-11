type ScreenViewProps = {
  frameSrc: string
  isWorking: boolean
  steeringFlashKey: number
  onExampleClick: (prompt: string) => void
  currentUrl: string
  pageTitle: string
}

const EXAMPLES = [
  'Go to Google and search for the latest AI news',
  'Open GitHub and star the top trending repo',
  'Navigate to Amazon and find wireless headphones under $50',
  'Go to Wikipedia and summarize the article on quantum computing',
]

export function ScreenView({ frameSrc, isWorking, steeringFlashKey, onExampleClick, currentUrl, pageTitle }: ScreenViewProps) {
  const showSteering = steeringFlashKey > 0 && isWorking
  const hasFrame = Boolean(frameSrc)

  return (
    <section className={`screen-view-container relative h-full min-h-[480px] overflow-hidden rounded-2xl border bg-[#1a1a1a] ${isWorking ? 'agent-active' : ''} ${showSteering ? 'agent-steer-flash' : ''}`}>
      <div className='absolute inset-x-0 top-0 z-20 h-0.5 bg-zinc-800'>
        <div className={`h-full bg-blue-500 transition-all ${isWorking ? 'w-full animate-pulse' : 'w-0'}`} />
      </div>

      <div className='absolute left-4 top-4 z-20 flex items-center gap-2 rounded-md border border-[#2a2a2a] bg-black/40 px-3 py-1 text-xs text-zinc-300'>
        <span className={`h-2 w-2 rounded-full ${isWorking ? 'bg-blue-400 animate-pulse' : 'bg-zinc-500'}`} />
        {isWorking ? 'Agent working...' : 'Agent idle'}
      </div>

      {showSteering && <div className='absolute left-4 top-12 z-20 rounded-md border border-blue-400/60 bg-blue-500/20 px-3 py-1 text-sm text-blue-200'>Steering received</div>}

      {hasFrame ? (
        <>
          <img src={frameSrc} alt='Live browser stream' className='h-full w-full object-contain opacity-100 transition-opacity duration-150 ease-in' />
          <div className='absolute inset-x-4 bottom-4 z-20 rounded-lg border border-[#2a2a2a] bg-black/50 px-3 py-2 text-xs text-zinc-200'>
            <p className='truncate font-medium'>{pageTitle || 'Untitled page'}</p>
            <p className='truncate text-zinc-400'>{currentUrl || 'about:blank'}</p>
          </div>
        </>
      ) : (
        <div className='flex h-full flex-col items-center justify-center px-8 text-center'>
          <img src='/shield.svg' alt='Aegis logo' className='mb-5 h-16 w-16 opacity-90' />
          <h2 className='text-3xl font-semibold'>Tell me what to do</h2>
          <p className='mb-8 mt-2 max-w-xl text-sm text-zinc-400'>Aegis can operate any UI with visual understanding. Start with a natural language instruction or choose an example below.</p>
          <div className='grid w-full max-w-3xl gap-3 md:grid-cols-2'>
            {EXAMPLES.map((prompt) => (
              <button key={prompt} type='button' onClick={() => onExampleClick(prompt)} className='rounded-xl border border-[#2a2a2a] bg-[#111] p-3 text-left text-sm text-zinc-200 transition hover:border-blue-500/60 hover:bg-zinc-900'>
                {prompt}
              </button>
            ))}
          </div>
          <p className='mt-5 text-xs text-zinc-500'>Connecting to browser...</p>
        </div>
      )}
    </section>
  )
}
