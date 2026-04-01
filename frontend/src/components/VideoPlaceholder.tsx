export function VideoPlaceholder({ className = '' }: { className?: string }) {
  return (
    <div
      className={`overflow-hidden rounded-2xl border border-[#1f1f1f] bg-[#0d1018] shadow-[0_20px_80px_rgba(0,0,0,0.35)] sm:rounded-[28px] ${className}`}
    >
      <div className='relative w-full' style={{ paddingBottom: '56.25%' }}>
        <img
          src='/og-image.png'
          alt='Aegis mobile app preview'
          className='absolute inset-0 h-full w-full object-cover'
        />
      </div>
    </div>
  )
}
