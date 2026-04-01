type VideoPlaceholderProps = {
  className?: string
  imageSrc?: string
}

export function VideoPlaceholder({ className = '', imageSrc = '/hero-image.png' }: VideoPlaceholderProps) {
  return (
    <div
      className={`overflow-hidden rounded-2xl border border-[#1f1f1f] bg-white shadow-[0_20px_80px_rgba(0,0,0,0.35)] sm:rounded-[28px] ${className}`}
    >
      <div className='relative w-full' style={{ paddingBottom: '56.25%' }}>
        <img
          src={imageSrc}
          alt='Aegis dual-phone bezel preview'
          className='absolute inset-0 h-full w-full object-contain'
        />
      </div>
    </div>
  )
}
