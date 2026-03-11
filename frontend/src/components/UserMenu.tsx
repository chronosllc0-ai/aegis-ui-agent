import { useState } from 'react'
import { Icons } from './icons'

type UserMenuProps = {
  name: string
  avatarUrl: string
  onOpenSettings: () => void
  onSignOut: () => void
}

export function UserMenu({ name, avatarUrl, onOpenSettings, onSignOut }: UserMenuProps) {
  const [open, setOpen] = useState(false)

  return (
    <div className='relative'>
      <button type='button' onClick={() => setOpen((prev) => !prev)} className='flex w-full items-center gap-2 rounded border border-[#2a2a2a] px-2 py-1'>
        <img src={avatarUrl || 'https://placehold.co/32x32'} alt='avatar' className='h-6 w-6 rounded-full' />
        <span className='text-xs'>{name}</span>
      </button>
      {open && (
        <div className='absolute bottom-10 right-0 z-20 w-48 rounded border border-[#2a2a2a] bg-[#111] p-1 text-xs'>
          <button type='button' onClick={onOpenSettings} className='inline-flex w-full items-center gap-2 rounded px-2 py-2 text-left hover:bg-zinc-800'>{Icons.settings({ className: 'h-3.5 w-3.5' })}Settings</button>
          <button type='button' onClick={onSignOut} className='inline-flex w-full items-center gap-2 rounded px-2 py-2 text-left text-red-300 hover:bg-zinc-800'>{Icons.logout({ className: 'h-3.5 w-3.5' })}Sign out</button>
        </div>
      )}
    </div>
  )
}
