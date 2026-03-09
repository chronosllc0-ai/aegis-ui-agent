import { useState } from 'react'

type UserMenuProps = {
  name: string
  avatarUrl: string
  onOpenSettings: () => void
}

export function UserMenu({ name, avatarUrl, onOpenSettings }: UserMenuProps) {
  const [open, setOpen] = useState(false)

  return (
    <div className='relative'>
      <button type='button' onClick={() => setOpen((prev) => !prev)} className='flex items-center gap-2 rounded border border-[#2a2a2a] px-2 py-1'>
        <img src={avatarUrl || 'https://placehold.co/32x32'} alt='avatar' className='h-6 w-6 rounded-full' />
        <span className='text-xs'>{name}</span>
      </button>
      {open && (
        <div className='absolute bottom-10 right-0 w-44 rounded border border-[#2a2a2a] bg-[#111] p-1 text-xs'>
          <button type='button' onClick={onOpenSettings} className='w-full rounded px-2 py-2 text-left hover:bg-zinc-800'>
            Settings
          </button>
        </div>
      )}
    </div>
  )
}
