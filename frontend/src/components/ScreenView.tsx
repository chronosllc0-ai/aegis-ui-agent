import { useEffect, useState } from 'react'

type ScreenViewProps = {
  frameSrc: string
  isWorking: boolean
  steeringFlashKey: number
}

export function ScreenView({ frameSrc, isWorking, steeringFlashKey }: ScreenViewProps) {
  const [showSteering, setShowSteering] = useState<boolean>(false)

  useEffect(() => {
    if (steeringFlashKey === 0) {
      return
    }
    setShowSteering(true)
    const timeout = window.setTimeout(() => setShowSteering(false), 900)
    return () => window.clearTimeout(timeout)
  }, [steeringFlashKey])

  return (
    <section className={`relative h-full min-h-[420px] rounded-xl border bg-[#1a1a1a] ${isWorking ? 'animate-pulse border-blue-500/70' : 'border-[#2a2a2a]'}`}>
      {showSteering && (
        <div className='absolute left-4 top-4 z-10 rounded-md border border-blue-400/60 bg-blue-500/20 px-3 py-1 text-sm text-blue-200'>
          Steering...
        </div>
      )}
      {frameSrc ? (
        <img src={frameSrc} alt='Live browser stream' className='h-full w-full rounded-xl object-contain' />
      ) : (
        <div className='flex h-full items-center justify-center text-sm text-zinc-400'>Waiting for first frame...</div>
      )}
    </section>
  )
}
