type VideoPlaceholderProps = {
  src?: string
  className?: string
}

export function VideoPlaceholder({ src, className = '' }: VideoPlaceholderProps) {
  return (
    <div
      className={`overflow-hidden rounded-2xl border border-[#1f1f1f] bg-[#0d1018] shadow-[0_20px_80px_rgba(0,0,0,0.35)] sm:rounded-[28px] ${className}`}
    >
      <div className='relative w-full' style={{ paddingBottom: '56.25%' }}>
        {src ? (
          <video
            src={src}
            controls
            className='absolute inset-0 h-full w-full object-cover'
          />
        ) : (
          <div className='absolute inset-0 flex flex-col items-center justify-center gap-4 bg-[#080b12]'>
            <div className='flex h-16 w-16 items-center justify-center rounded-full border border-cyan-400/30 bg-cyan-400/8'>
              <svg
                viewBox='0 0 24 24'
                fill='none'
                className='h-7 w-7 text-cyan-300'
                aria-hidden='true'
              >
                <path d='m9 7 9 5-9 5z' fill='currentColor' />
              </svg>
            </div>
            <p className='text-sm text-zinc-400'>Demo video coming soon</p>
          </div>
        )}
      </div>
    </div>
  )
}
