type ScreenViewProps = {
  frameSrc: string
  isWorking: boolean
}

export function ScreenView({ frameSrc, isWorking }: ScreenViewProps) {
  return (
    <section className='relative h-full min-h-[420px] rounded-xl border border-[#2a2a2a] bg-[#1a1a1a]'>
      <div className='absolute inset-x-0 top-0 h-0.5 bg-zinc-800'>
        <div className={`h-full bg-blue-500 transition-all ${isWorking ? 'w-full animate-pulse' : 'w-0'}`} />
      </div>
      {frameSrc ? (
        <img src={frameSrc} alt='Live browser stream' className='h-full w-full rounded-xl object-contain' />
      ) : (
        <div className='flex h-full items-center justify-center text-zinc-400'>Waiting for first frame...</div>
      )}
    </section>
  )
}
