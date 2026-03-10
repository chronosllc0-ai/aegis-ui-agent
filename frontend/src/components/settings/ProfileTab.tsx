import type { AppSettings } from '../../hooks/useSettings'

type ProfileTabProps = {
  settings: AppSettings
  onPatch: (next: Partial<AppSettings>) => void
}

export function ProfileTab({ settings, onPatch }: ProfileTabProps) {
  return (
    <div className='space-y-4'>
      <label className='block text-sm'>
        Display Name
        <input value={settings.displayName} onChange={(event) => onPatch({ displayName: event.target.value })} className='mt-1 w-full rounded border border-[#2a2a2a] bg-[#111] px-3 py-2' />
      </label>
      <label className='block text-sm'>
        Avatar URL
        <input value={settings.avatarUrl} onChange={(event) => onPatch({ avatarUrl: event.target.value })} className='mt-1 w-full rounded border border-[#2a2a2a] bg-[#111] px-3 py-2' />
      </label>
      <label className='block text-sm'>
        Email
        <input value={settings.email} readOnly className='mt-1 w-full rounded border border-[#2a2a2a] bg-[#111] px-3 py-2 opacity-70' />
      </label>
      <div className='flex gap-2'>
        {(['dark', 'light', 'system'] as const).map((theme) => (
          <button key={theme} type='button' onClick={() => onPatch({ theme })} className={`rounded px-3 py-1 text-xs capitalize ${settings.theme === theme ? 'bg-blue-600' : 'border border-[#2a2a2a]'}`}>
            {theme}
          </button>
        ))}
      </div>
      <button type='button' className='rounded border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-300'>Delete Account</button>
    </div>
  )
}
