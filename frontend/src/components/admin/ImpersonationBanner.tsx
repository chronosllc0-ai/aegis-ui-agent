import { useCallback, useState } from 'react'
import { LuTriangleAlert } from 'react-icons/lu'
import { apiUrl } from '../../lib/api'

type ImpersonationBannerProps = {
  email: string
}

export function ImpersonationBanner({ email }: ImpersonationBannerProps) {
  const [exiting, setExiting] = useState(false)

  const handleExit = useCallback(async () => {
    setExiting(true)
    try {
      await fetch(apiUrl('/api/admin/impersonate/stop'), {
        method: 'POST',
        credentials: 'include',
      })
      window.location.href = '/admin/users'
    } catch {
      setExiting(false)
    }
  }, [])

  return (
    <div className='fixed inset-x-0 top-0 z-50 flex items-center justify-center gap-3 border-b border-amber-500/30 bg-amber-500/10 px-4 py-2 text-sm backdrop-blur-sm'>
      <LuTriangleAlert className='h-4 w-4 text-amber-400' />
      <span className='text-amber-200'>
        You are viewing as <strong className='text-amber-100'>{email}</strong>
      </span>
      <button
        type='button'
        onClick={handleExit}
        disabled={exiting}
        className='rounded-md border border-amber-500/40 bg-amber-500/20 px-3 py-1 text-xs font-medium text-amber-100 hover:bg-amber-500/30 disabled:opacity-50'
      >
        {exiting ? 'Exiting...' : 'Exit Impersonation'}
      </button>
    </div>
  )
}
