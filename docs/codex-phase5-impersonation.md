# Codex Phase 5: Impersonation Integration + Polish

## Project Context
Aegis is a FastAPI + React/TypeScript app. Phases 1-4 added: RBAC on User model, admin API endpoints, conversation persistence, React Router, admin panel with sidebar + detail panels. The impersonation backend endpoints exist (`POST /api/admin/impersonate/start`, `POST /api/admin/impersonate/stop`, `GET /api/admin/impersonate/status`). The `ImpersonationBanner` component exists. Now we need to wire it all together.

## What to implement
Connect impersonation flow end-to-end: admin initiates from user detail panel, sees target user's actual client dashboard, amber banner shows on all pages, exit returns to admin panel. Plus final polish.

## CRITICAL RULES
- Do NOT use emojis as icons. Use react-icons/lu only.
- Do NOT modify: `orchestrator.py`, `session.py`, `navigator.py`, `analyzer.py`, `executor.py`, `backend/providers/*`, `backend/credit_rates.py`, `backend/credit_service.py`, `LandingPage.tsx`, `InputBar.tsx`, `ScreenView.tsx`, `ActionLog.tsx`
- Match exact dark theme: `bg-[#111]`, `bg-[#1a1a1a]`, `border-[#2a2a2a]`
- ESLint strict: no setState in useEffect bodies, no ref access during render

---

## 1. Wire impersonation into UserDetailPanel

In `frontend/src/admin/pages/UserDetailPanel.tsx`, add a "View as User" button:

```tsx
// In the Overview tab or header area:
<button
  type="button"
  onClick={() => handleImpersonate(user.uid)}
  className="flex items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-2 text-sm text-amber-300 hover:bg-amber-500/20"
>
  <LuEye className="h-4 w-4" />
  View as User
</button>
```

The handler should:
1. Show a confirmation dialog (simple `window.confirm` is fine):
   "You will switch to [user email]'s account. All actions will be logged. Continue?"
2. Call `POST /api/admin/impersonate/start` with `{ target: user.uid }`
3. On success, `window.location.href = '/app'` (full page reload to pick up new session)

## 2. Wire ImpersonationBanner in App.tsx

The `ImpersonationBanner` should already be rendered conditionally in App.tsx (from Phase 4). Verify:

```tsx
// In App.tsx, before <Routes>:
{isImpersonating && <ImpersonationBanner email={authUser?.email ?? ''} />}
```

Where `isImpersonating` comes from the auth response:
```tsx
const isImpersonating = authUser?.impersonating === true
```

The banner is a fixed bar at the very top of the viewport. When it's showing, the rest of the layout needs `pt-10` (or whatever the banner height is) to avoid being hidden underneath.

## 3. Update ImpersonationBanner component

Ensure `frontend/src/admin/components/ImpersonationBanner.tsx` has:

```tsx
import { useCallback, useState } from 'react'
import { LuTriangleAlert, LuX } from 'react-icons/lu'
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
    <div className="fixed inset-x-0 top-0 z-50 flex items-center justify-center gap-3 border-b border-amber-500/30 bg-amber-500/10 px-4 py-2 text-sm backdrop-blur-sm">
      <LuTriangleAlert className="h-4 w-4 text-amber-400" />
      <span className="text-amber-200">
        You are viewing as <strong className="text-amber-100">{email}</strong>
      </span>
      <button
        type="button"
        onClick={handleExit}
        disabled={exiting}
        className="rounded-md border border-amber-500/40 bg-amber-500/20 px-3 py-1 text-xs font-medium text-amber-100 hover:bg-amber-500/30 disabled:opacity-50"
      >
        {exiting ? 'Exiting...' : 'Exit Impersonation'}
      </button>
    </div>
  )
}
```

## 4. Offset content when impersonating

When the impersonation banner is showing (40px tall, fixed), add top padding to the main layout:

In `App.tsx`:
```tsx
<div className={isImpersonating ? 'pt-10' : ''}>
  <Routes>
    {/* ... */}
  </Routes>
</div>
```

OR pass `isImpersonating` as a prop to `ClientDashboard` and `AdminLayout` so they can add the padding themselves. The key is that content isn't hidden behind the banner.

## 5. Also show banner on admin pages

When an admin is impersonating and navigates to `/admin/*`, the banner should still show. The impersonating state is checked via `authUser.impersonating` which persists across routes since it comes from the session cookie.

The Routes rendering in App.tsx should allow admins to access `/admin` even while impersonating (they might navigate there via the browser). The banner shows regardless.

## 6. Update `useImpersonation` hook

Ensure `frontend/src/admin/hooks/useImpersonation.ts` has:

```tsx
import { useCallback, useState } from 'react'
import { apiUrl } from '../../lib/api'

type ImpersonationStatus = {
  impersonating: boolean
  target_user?: { uid: string; email: string; name: string }
  admin_uid?: string
}

export function useImpersonation() {
  const [status, setStatus] = useState<ImpersonationStatus | null>(null)
  const [loading, setLoading] = useState(false)

  const checkStatus = useCallback(async () => {
    try {
      const res = await fetch(apiUrl('/api/admin/impersonate/status'), { credentials: 'include' })
      if (res.ok) {
        const data = await res.json()
        setStatus(data)
      }
    } catch {
      // Ignore
    }
  }, [])

  const startImpersonation = useCallback(async (target: string): Promise<boolean> => {
    setLoading(true)
    try {
      const res = await fetch(apiUrl('/api/admin/impersonate/start'), {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target }),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.detail || 'Impersonation failed')
      }
      return true
    } catch {
      return false
    } finally {
      setLoading(false)
    }
  }, [])

  const stopImpersonation = useCallback(async (): Promise<boolean> => {
    setLoading(true)
    try {
      const res = await fetch(apiUrl('/api/admin/impersonate/stop'), {
        method: 'POST',
        credentials: 'include',
      })
      return res.ok
    } catch {
      return false
    } finally {
      setLoading(false)
    }
  }, [])

  return { status, loading, checkStatus, startImpersonation, stopImpersonation }
}
```

## 7. Admin users page — add "View as User" quick action

In `frontend/src/admin/pages/UsersPage.tsx`, each user row should have a quick action button:

```tsx
<button
  type="button"
  onClick={(e) => {
    e.stopPropagation()
    if (window.confirm(`Switch to ${user.email}'s account? All actions will be logged.`)) {
      handleImpersonate(user.uid)
    }
  }}
  className="rounded p-1 text-zinc-400 hover:bg-zinc-800 hover:text-amber-300"
  title="View as user"
>
  <LuEye className="h-4 w-4" />
</button>
```

Where `handleImpersonate` calls the hook's `startImpersonation` and then does `window.location.href = '/app'`.

## 8. Polish: Admin navigation from client side

In `ClientDashboard.tsx` (or wherever the sidebar is), if the user has `role === 'admin'` or `role === 'superadmin'`, show an "Admin Panel" link in the sidebar:

```tsx
{isAdmin && (
  <button
    type="button"
    onClick={() => navigate('/admin')}
    className="flex w-full items-center gap-2 rounded border border-[#2a2a2a] px-2 py-2 text-left text-xs text-zinc-300 hover:bg-zinc-800"
  >
    <LuShield className="h-3.5 w-3.5" />
    <span>Admin Panel</span>
  </button>
)}
```

The `isAdmin` check uses the `authUser.role` prop passed to ClientDashboard.

## 9. Polish: Loading states

All admin pages should show a loading skeleton while data is being fetched:

```tsx
{loading && (
  <div className="flex items-center justify-center py-12">
    <LuLoader className="h-6 w-6 animate-spin text-zinc-500" />
  </div>
)}
```

## 10. Polish: Empty states

When there's no data (no users matching search, no conversations, no audit entries):

```tsx
{!loading && items.length === 0 && (
  <div className="flex flex-col items-center justify-center py-12 text-center">
    <LuSearch className="mb-2 h-8 w-8 text-zinc-600" />
    <p className="text-sm text-zinc-500">No results found</p>
  </div>
)}
```

---

## Verification
1. `cd frontend && npm run build` — zero errors
2. `cd frontend && npm run lint` — zero errors
3. Admin can click "View as User" → sees target user's client dashboard
4. Amber banner shows at top on all pages during impersonation
5. "Exit Impersonation" button returns to admin panel
6. Admin link shows in client sidebar for admin users
7. No emojis anywhere — only react-icons
8. All existing client functionality still works
9. Content is not hidden behind impersonation banner
