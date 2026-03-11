import { useMemo, useState } from 'react'
import type { AppSettings } from '../../hooks/useSettings'

type ProfileTabProps = {
  settings: AppSettings
  onPatch: (next: Partial<AppSettings>) => void
}

export function ProfileTab({ settings, onPatch }: ProfileTabProps) {
  const [draft, setDraft] = useState({
    displayName: settings.displayName,
    avatarUrl: settings.avatarUrl,
    theme: settings.theme,
  })
  const [savedNotice, setSavedNotice] = useState<string | null>(null)

  const preview = useMemo(() => draft.avatarUrl || 'https://placehold.co/96x96/111827/ffffff?text=A', [draft.avatarUrl])

  const save = () => {
    onPatch(draft)
    setSavedNotice('Profile settings saved.')
    window.setTimeout(() => setSavedNotice(null), 2200)
  }

  const reset = () => {
    setDraft({
      displayName: settings.displayName,
      avatarUrl: settings.avatarUrl,
      theme: settings.theme,
    })
  }

  return (
    <div className='mx-auto max-w-4xl space-y-6'>
      <header>
        <h3 className='text-lg font-semibold'>Profile</h3>
        <p className='text-sm text-zinc-400'>Manage account identity, theme preference, and profile presentation.</p>
      </header>

      <section className='rounded-2xl border border-[#2a2a2a] bg-[#111] p-5'>
        <div className='grid gap-6 md:grid-cols-[160px_1fr]'>
          <div className='space-y-2 text-center'>
            <img src={preview} alt='Avatar preview' className='mx-auto h-24 w-24 rounded-full border border-[#2a2a2a] object-cover' />
            <p className='text-xs text-zinc-500'>Avatar preview</p>
            <button type='button' className='w-full rounded-md border border-[#2a2a2a] px-2 py-1 text-xs hover:bg-zinc-900'>Upload</button>
          </div>

          <div className='space-y-4'>
            <label className='block text-sm'>
              Display Name
              <input value={draft.displayName} onChange={(event) => setDraft((prev) => ({ ...prev, displayName: event.target.value }))} className='mt-1 w-full rounded-lg border border-[#2a2a2a] bg-[#0c0c0c] px-3 py-2' />
            </label>

            <label className='block text-sm'>
              Avatar URL
              <input value={draft.avatarUrl} onChange={(event) => setDraft((prev) => ({ ...prev, avatarUrl: event.target.value }))} className='mt-1 w-full rounded-lg border border-[#2a2a2a] bg-[#0c0c0c] px-3 py-2' />
            </label>

            <label className='block text-sm'>
              Email
              <input value={settings.email} readOnly className='mt-1 w-full rounded-lg border border-[#2a2a2a] bg-[#0c0c0c] px-3 py-2 opacity-70' />
            </label>

            <div>
              <p className='mb-2 text-sm'>Theme</p>
              <div className='flex gap-2'>
                {(['dark', 'light', 'system'] as const).map((theme) => (
                  <button key={theme} type='button' onClick={() => setDraft((prev) => ({ ...prev, theme }))} className={`rounded-md px-3 py-1 text-xs capitalize ${draft.theme === theme ? 'bg-blue-600 text-white' : 'border border-[#2a2a2a] text-zinc-300'}`}>
                    {theme}
                  </button>
                ))}
              </div>
            </div>

            <div className='flex items-center gap-2'>
              <button type='button' onClick={save} className='rounded-md bg-blue-600 px-4 py-2 text-sm'>Save changes</button>
              <button type='button' onClick={reset} className='rounded-md border border-[#2a2a2a] px-4 py-2 text-sm'>Reset</button>
              {savedNotice && <span className='text-xs text-emerald-300'>{savedNotice}</span>}
            </div>
          </div>
        </div>
      </section>

      <section className='rounded-2xl border border-red-500/30 bg-red-500/5 p-5'>
        <h4 className='text-sm font-semibold text-red-300'>Danger Zone</h4>
        <p className='mt-1 text-xs text-zinc-400'>Delete account permanently including saved workflows and integration links.</p>
        <button type='button' className='mt-3 rounded-md border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-300'>Delete Account</button>
      </section>
    </div>
  )
}
