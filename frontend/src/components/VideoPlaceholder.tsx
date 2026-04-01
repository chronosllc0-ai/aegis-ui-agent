type VideoPlaceholderProps = {
  className?: string
  src?: string
}

export function VideoPlaceholder({ className = '', src }: VideoPlaceholderProps) {
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
          <div className='absolute inset-0'>
            <img
              src='/og-image.png'
              alt='Aegis mobile demo preview'
              className='h-full w-full object-cover'
            />
            <div className='absolute inset-0 bg-gradient-to-t from-[#06080d]/75 via-transparent to-transparent' />
            <div className='absolute bottom-5 left-5 right-5 flex items-center gap-3 rounded-xl border border-white/10 bg-[#070b12]/70 p-3 backdrop-blur-md'>
              <div className='flex h-11 w-11 shrink-0 items-center justify-center rounded-full border border-cyan-400/30 bg-cyan-400/12'>
                <svg viewBox='0 0 24 24' fill='none' className='h-5 w-5 text-cyan-300' aria-hidden='true'>
                  <path d='m9 7 9 5-9 5z' fill='currentColor' />
                </svg>
              </div>
              <p className='text-xs text-zinc-200 sm:text-sm'>Watch Aegis run end-to-end workflows across browser, code, and integrations.</p>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
