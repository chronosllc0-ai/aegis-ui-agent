# Codex Phase 4: Admin Frontend Panel

## Project Context
Aegis is a FastAPI + React/TypeScript app. Frontend at `frontend/` uses Vite + React + TypeScript + Tailwind v4. Currently has no router library — `App.tsx` uses state flags to switch between LandingPage, AuthPage, and the main dashboard. The backend admin API is fully implemented (Phases 1-3).

## What to implement
Install react-router-dom, refactor App.tsx to use routes, create the admin panel with collapsible sidebar and slide-out detail panels, and implement all admin pages.

## CRITICAL RULES
- Do NOT use emojis as icons ANYWHERE. Use `react-icons/lu` (Lucide) for all icons.
- The frontend uses Tailwind v4. Dark theme colors: `bg-[#111]` (background), `bg-[#1a1a1a]` (cards), `bg-[#171717]` (sidebar), `border-[#2a2a2a]` (borders), `text-zinc-*` (text). Match exactly.
- ESLint is strict: NO `setState` in `useEffect` bodies, NO ref access during render. Use derived state patterns.
- Use `apiUrl('/path')` from `frontend/src/lib/api.ts` for ALL API calls.
- Import icons directly from react-icons: `import { LuLayoutDashboard, LuUsers } from 'react-icons/lu'`
- Do NOT modify these files: `LandingPage.tsx`, `InputBar.tsx`, `ScreenView.tsx`, `ActionLog.tsx`, `WorkflowView.tsx`, `UsageMeterBar.tsx`, `CostEstimator.tsx`, `CreditBadge.tsx`, `SpendingAlert.tsx`, `useSettings.ts`, `useMicrophone.ts`, `useUsage.ts`, `useWebSocket.ts`, `models.ts`, `creditRates.ts`, `mcp.ts`, `icons.tsx`, anything in `settings/`
- The existing client dashboard MUST continue working exactly as before at `/app`
- All existing functionality (WebSocket, InputBar, ScreenView, ActionLog, settings, usage, BYOK) must be preserved

## Current frontend dependencies
```json
{
  "react": "^19.0.0",
  "react-dom": "^19.0.0",
  "react-icons": "^4.12.0"
}
```

## Verified react-icons/lu names (some differ from docs)
- `LuLayoutDashboard` (dashboard)
- `LuUsers` (users)
- `LuCreditCard` (billing)
- `LuMessageSquare` (conversations)
- `LuBot` (agents)
- `LuShield` (audit/security)
- `LuSettings` (settings)
- `LuArrowLeftRight` (switch views)
- `LuSearch` (search)
- `LuChevronLeft`, `LuChevronRight` (collapse)
- `LuX` (close)
- `LuPanelLeftOpen`, `LuPanelLeftClose` (sidebar toggle)
- `LuTriangleAlert` (NOT `LuAlertTriangle`)
- `LuChartBar` (NOT `LuBarChart3`)
- `LuLoader` (NOT `LuLoader2`)
- `LuFilter` (filter)
- `LuDownload` (export)
- `LuEye` (view)
- `LuPencil` (edit)
- `LuBan` (suspend)
- `LuCheck` (active/approve)
- `LuMoreVertical` (menu)

---

## 1. Install react-router-dom

Add to `frontend/package.json` dependencies:
```json
"react-router-dom": "^7.4.0"
```

Run `npm install` to update `package-lock.json`.

## 2. Modify `frontend/src/main.tsx`

```tsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import { SettingsProvider } from './context/SettingsContext'
import './index.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <SettingsProvider>
        <App />
      </SettingsProvider>
    </BrowserRouter>
  </StrictMode>,
)
```

## 3. Refactor `frontend/src/App.tsx`

### 3a. Extract the client dashboard

Move the entire authenticated main view (everything inside the `return` block when `isAuthenticated` is true) into a new component: `frontend/src/components/ClientDashboard.tsx`.

This component receives all the same props/hooks the current view uses. It's a pure extraction — NO logic changes.

The ClientDashboard component should:
- Accept props for all the state and handlers it needs (or use the hooks directly inside it)
- Render the sidebar, header, usage bar, URL bar, screen/action split, input bar, cost estimator, spending alert
- Be functionally identical to the current authenticated view

### 3b. Rewrite App.tsx with routes

```tsx
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Navigate, Route, Routes, useNavigate } from 'react-router-dom'
import { AuthPage } from './components/AuthPage'
import { LandingPage } from './components/LandingPage'
import { ClientDashboard } from './components/ClientDashboard'
import { AdminLayout } from './admin/AdminLayout'
import { ImpersonationBanner } from './admin/components/ImpersonationBanner'
import { apiUrl } from './lib/api'

type AuthUser = {
  uid: string
  name: string
  email: string
  avatar_url?: string | null
  role?: string
  impersonating?: boolean
  admin_uid?: string
}

function App() {
  const navigate = useNavigate()
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [authUser, setAuthUser] = useState<AuthUser | null>(null)
  const [authLoading, setAuthLoading] = useState(true)

  useEffect(() => {
    let active = true
    const loadAuth = async () => {
      setAuthLoading(true)
      try {
        const response = await fetch(apiUrl('/api/auth/me'), { credentials: 'include' })
        if (!response.ok) {
          if (active) {
            setIsAuthenticated(false)
            setAuthUser(null)
          }
          return
        }
        const data = await response.json().catch(() => ({}))
        if (active && data?.user) {
          setAuthUser(data.user)
          setIsAuthenticated(true)
        }
      } finally {
        if (active) setAuthLoading(false)
      }
    }
    void loadAuth()
    return () => { active = false }
  }, [])

  const handleAuth = useCallback((user: AuthUser) => {
    setAuthUser(user)
    setIsAuthenticated(true)
    // Auto-redirect based on role
    if (user.role === 'admin' || user.role === 'superadmin') {
      navigate('/admin')
    } else {
      navigate('/app')
    }
  }, [navigate])

  const handleSignOut = useCallback(async () => {
    await fetch(apiUrl('/api/auth/logout'), { method: 'POST', credentials: 'include' })
    setAuthUser(null)
    setIsAuthenticated(false)
    navigate('/')
  }, [navigate])

  const isAdmin = authUser?.role === 'admin' || authUser?.role === 'superadmin'
  const isImpersonating = authUser?.impersonating === true

  if (authLoading) {
    return (
      <main className='flex h-screen items-center justify-center bg-[#111] text-zinc-100'>
        <div className='rounded-full border border-[#2a2a2a] bg-[#1a1a1a] px-4 py-2 text-sm text-zinc-400'>Checking session...</div>
      </main>
    )
  }

  return (
    <>
      {isImpersonating && <ImpersonationBanner email={authUser?.email ?? ''} />}
      <Routes>
        <Route path="/" element={
          !isAuthenticated
            ? <LandingPage onGetStarted={() => navigate('/auth')} />
            : <Navigate to={isAdmin ? '/admin' : '/app'} replace />
        } />
        <Route path="/auth" element={
          !isAuthenticated
            ? <AuthPage onAuthenticated={handleAuth} onBack={() => navigate('/')} />
            : <Navigate to={isAdmin ? '/admin' : '/app'} replace />
        } />
        <Route path="/app/*" element={
          isAuthenticated
            ? <ClientDashboard authUser={authUser} onSignOut={handleSignOut} onOpenSettings={() => {}} />
            : <Navigate to="/auth" replace />
        } />
        <Route path="/admin/*" element={
          isAuthenticated && isAdmin
            ? <AdminLayout authUser={authUser} onSignOut={handleSignOut} />
            : <Navigate to={isAuthenticated ? '/app' : '/auth'} replace />
        } />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </>
  )
}

export default App
```

**IMPORTANT**: The `ClientDashboard` component must contain ALL the existing hooks (`useWebSocket`, `useUsage`, `useSettingsContext`, `useMicrophone`) and ALL the existing UI (sidebar, header, usage bar, URL bar, ScreenView, ActionLog, InputBar, settings, etc.). It must be a direct extraction of the current `App.tsx` authenticated view with zero logic changes.

## 4. Create `frontend/src/admin/AdminLayout.tsx`

The admin layout has three parts:
1. **Collapsible left sidebar** — slides left/right. Contains nav links with Lucide icons.
2. **Main content area** — renders the active admin page via nested routes
3. **Slide-out detail panel** — context-provided, slides from right edge

```tsx
import { useState } from 'react'
import { NavLink, Route, Routes, useNavigate } from 'react-router-dom'
import {
  LuLayoutDashboard, LuUsers, LuCreditCard, LuMessageSquare,
  LuBot, LuShield, LuSettings, LuArrowLeftRight, LuPanelLeftOpen, LuPanelLeftClose,
} from 'react-icons/lu'
import { DashboardPage } from './pages/DashboardPage'
import { UsersPage } from './pages/UsersPage'
import { BillingPage } from './pages/BillingPage'
import { ConversationsPage } from './pages/ConversationsPage'
import { AgentsPage } from './pages/AgentsPage'
import { AuditPage } from './pages/AuditPage'
import { AdminSettingsPage } from './pages/AdminSettingsPage'
import { DetailPanelProvider, useDetailPanel } from './DetailPanelContext'

// ... layout component with sidebar toggle, nav items, main area, and detail panel overlay
```

Sidebar nav items (each is a `NavLink`):
```
/admin           → LuLayoutDashboard  Dashboard
/admin/users     → LuUsers            Users
/admin/billing   → LuCreditCard       Billing
/admin/conversations → LuMessageSquare Conversations
/admin/agents    → LuBot              Agents
/admin/audit     → LuShield           Audit Log
/admin/settings  → LuSettings         Settings
```

Plus a "Switch to App" link at the bottom → navigates to `/app`.

**Sidebar style:**
- Width: 240px expanded, 56px collapsed (icon only)
- `bg-[#171717] border-r border-[#2a2a2a]`
- Active item: `bg-blue-600 text-white rounded-lg`
- Inactive: `text-zinc-400 hover:bg-[#222] hover:text-zinc-200 rounded-lg`
- Toggle button uses `LuPanelLeftOpen`/`LuPanelLeftClose`
- On mobile (<md): overlay with backdrop, toggle to show/hide

**Detail panel:**
- Use a React Context (`DetailPanelContext`) so any page can open/close it
- Slides from right, width 480px, `bg-[#1a1a1a] border-l border-[#2a2a2a]`
- Has close button (LuX) in top-right
- Content is set via context: `openDetailPanel(reactNode)`
- Backdrop: `bg-black/30` click-to-close

## 5. Create admin pages

### `frontend/src/admin/pages/DashboardPage.tsx`
- Fetch `GET /api/admin/dashboard` on mount
- Grid of StatsCard components: Total Users, Active (7d), New This Month, Credits Used, Active Conversations
- Each StatsCard: icon (from react-icons/lu) + label + large number, card style `bg-[#1a1a1a] border border-[#2a2a2a] rounded-xl p-4`
- Recent activity list from the dashboard response
- Simple platform breakdown (colored div bars, no chart library)

### `frontend/src/admin/pages/UsersPage.tsx`
- Search input + role filter dropdown + status filter dropdown
- Fetch `GET /api/admin/users?search=...&role=...&status=...&limit=50&offset=0`
- Table with columns: User (avatar + name + email), Role (badge), Status (badge), Plan, Last Login, Actions
- Row click → opens `UserDetailPanel` in the detail panel context
- Quick action buttons per row: eye icon (view), ban icon (suspend), check icon (reinstate)
- Pagination: Previous/Next buttons with offset tracking

### `frontend/src/admin/pages/UserDetailPanel.tsx`
- Renders inside the slide-out detail panel
- Receives `uid` prop, fetches `GET /api/admin/users/{uid}`
- Header: avatar circle (initials if no avatar_url), name, email, role badge, status badge
- Tabs: Overview | Billing | Conversations | Usage
- **Overview tab**: Info grid (created, last login, provider), edit form (name, email), role selector (admin/user — superadmin only), action buttons (suspend/reinstate)
- **Billing tab**: payment methods list, add form (type, brand, last4, exp), plan selector (Free/Pro/Team), credit adjustment input
- **Conversations tab**: list conversations for this user, click to navigate to conversation viewer
- **Usage tab**: credit balance display, recent usage events

### `frontend/src/admin/pages/ConversationsPage.tsx`
- Filter bar: platform dropdown (All/Web/Telegram/Slack/Discord), user search input, date range
- Fetch `GET /api/admin/conversations?platform=...&search=...`
- List of conversation cards: user avatar+name, platform badge (colored), title, message count, last activity
- Click opens conversation in detail panel

### `frontend/src/admin/pages/ConversationViewer.tsx`
- Renders in detail panel
- Fetches `GET /api/admin/conversations/{id}`
- Header: platform badge, user info, title, date
- Chat-style message list: user messages right-aligned (blue bg), assistant left-aligned (gray bg), system centered
- Timestamp on each message
- Load more button at top for pagination

### `frontend/src/admin/pages/AuditPage.tsx`
- Filter bar: admin dropdown, action type dropdown, target user search, date range
- Fetch `GET /api/admin/audit?...`
- Table: Timestamp, Admin, Action, Target User, Details preview, IP
- Click row to expand and show full JSON details

### `frontend/src/admin/pages/BillingPage.tsx`
- Overview cards: total paying users, estimated MRR
- Quick user search to jump to user billing
- Link to user detail panel's billing tab

### `frontend/src/admin/pages/AgentsPage.tsx`
- Simple page showing global agent configuration
- Default model, default system instruction, default temperature
- Save button to update (future — can be read-only for now)

### `frontend/src/admin/pages/AdminSettingsPage.tsx`
- Admin management section (superadmin only)
- List current admins/superadmins
- "Add admin by email" input
- Global settings (ADMIN_EMAILS display, system defaults)

## 6. Create shared admin components

### `frontend/src/admin/components/StatsCard.tsx`
```tsx
type StatsCardProps = {
  icon: React.ReactNode
  label: string
  value: string | number
}
// Renders a card with icon, label, and large value
```

### `frontend/src/admin/components/PlatformBadge.tsx`
```tsx
type PlatformBadgeProps = { platform: string }
// Colored badge: web=blue, telegram=sky, slack=purple, discord=indigo
```

### `frontend/src/admin/components/RoleBadge.tsx`
```tsx
type RoleBadgeProps = { role: string }
// Colored pill: user=zinc, admin=blue, superadmin=amber
```

### `frontend/src/admin/components/StatusBadge.tsx`
```tsx
type StatusBadgeProps = { status: string }
// active=green, suspended=yellow, banned=red
```

### `frontend/src/admin/components/ImpersonationBanner.tsx`
- Fixed at top of viewport, z-50
- `bg-amber-500/10 border-b border-amber-500/30`
- Text: "You are viewing as {email}"
- "Exit" button → `POST /api/admin/impersonate/stop` then `window.location.reload()`
- 40px height, full width

## 7. Create admin hooks in `frontend/src/admin/hooks/`

Each hook handles API calls to the admin endpoints. Pattern:

```tsx
// useAdminUsers.ts
export function useAdminUsers() {
  const [users, setUsers] = useState<AdminUser[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)

  const fetchUsers = useCallback(async (params: UserSearchParams) => {
    setLoading(true)
    try {
      const qs = new URLSearchParams(/* ... */)
      const res = await fetch(apiUrl(`/api/admin/users?${qs}`), { credentials: 'include' })
      const data = await res.json()
      setUsers(data.users)
      setTotal(data.total)
    } finally {
      setLoading(false)
    }
  }, [])

  // ... updateUser, suspendUser, reinstateUser, adjustCredits

  return { users, total, loading, fetchUsers, /* ... */ }
}
```

Create these hooks:
- `useAdminUsers.ts` — fetch, search, update, suspend, reinstate, credit adjustment
- `useAdminBilling.ts` — payment method CRUD, plan changes
- `useAdminConversations.ts` — fetch, search conversations, get messages
- `useAdminAudit.ts` — fetch audit log with filters
- `useAdminDashboard.ts` — fetch dashboard stats
- `useImpersonation.ts` — start, stop, check impersonation status

## 8. Create `frontend/src/admin/DetailPanelContext.tsx`

React context for the slide-out detail panel:
```tsx
import { createContext, useCallback, useContext, useState, type ReactNode } from 'react'

type DetailPanelContextType = {
  content: ReactNode | null
  isOpen: boolean
  openPanel: (content: ReactNode) => void
  closePanel: () => void
}

const DetailPanelContext = createContext<DetailPanelContextType>({
  content: null,
  isOpen: false,
  openPanel: () => {},
  closePanel: () => {},
})

export function DetailPanelProvider({ children }: { children: ReactNode }) {
  const [content, setContent] = useState<ReactNode | null>(null)
  const [isOpen, setIsOpen] = useState(false)

  const openPanel = useCallback((node: ReactNode) => {
    setContent(node)
    setIsOpen(true)
  }, [])

  const closePanel = useCallback(() => {
    setIsOpen(false)
    setContent(null)
  }, [])

  return (
    <DetailPanelContext.Provider value={{ content, isOpen, openPanel, closePanel }}>
      {children}
    </DetailPanelContext.Provider>
  )
}

export function useDetailPanel() {
  return useContext(DetailPanelContext)
}
```

---

## File structure summary

```
frontend/src/
├── admin/
│   ├── AdminLayout.tsx
│   ├── DetailPanelContext.tsx
│   ├── components/
│   │   ├── ImpersonationBanner.tsx
│   │   ├── PlatformBadge.tsx
│   │   ├── RoleBadge.tsx
│   │   ├── StatsCard.tsx
│   │   └── StatusBadge.tsx
│   ├── hooks/
│   │   ├── useAdminAudit.ts
│   │   ├── useAdminBilling.ts
│   │   ├── useAdminConversations.ts
│   │   ├── useAdminDashboard.ts
│   │   ├── useAdminUsers.ts
│   │   └── useImpersonation.ts
│   └── pages/
│       ├── AdminSettingsPage.tsx
│       ├── AgentsPage.tsx
│       ├── AuditPage.tsx
│       ├── BillingPage.tsx
│       ├── ConversationViewer.tsx
│       ├── ConversationsPage.tsx
│       ├── DashboardPage.tsx
│       ├── UserDetailPanel.tsx
│       └── UsersPage.tsx
├── components/
│   ├── ClientDashboard.tsx  ← NEW (extracted from App.tsx)
│   └── ... (existing, unchanged)
├── App.tsx  ← MODIFIED (router-based)
└── main.tsx  ← MODIFIED (BrowserRouter wrapper)
```

---

## Verification
1. `cd frontend && npm install` — installs react-router-dom
2. `cd frontend && npm run build` — zero errors
3. `cd frontend && npm run lint` — zero errors
4. Landing page at `/` still works
5. Auth page at `/auth` still works
6. Client dashboard at `/app` has ALL existing functionality (WebSocket, InputBar, ScreenView, ActionLog, settings, BYOK, usage meter, etc.)
7. Admin panel at `/admin` shows dashboard
8. Navigation between admin pages works
9. Detail panel slides in/out when clicking user rows
10. No emojis anywhere — only react-icons
