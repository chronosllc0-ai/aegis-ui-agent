import { useCallback, useEffect, useState } from 'react'
import { LuEye, LuLoader, LuSearch } from 'react-icons/lu'
import { Icons } from '../icons'
import { useToast } from '../../hooks/useToast'
import { apiUrl } from '../../lib/api'
import { AdminMessaging } from './AdminMessaging'
import { AdminEmailing } from './AdminEmailing'
import { PaymentSettingsModal } from './PaymentSettingsModal'
import { useImpersonation } from './useImpersonation'

/* ─── Types ─────────────────────────────────────────────────────────── */

type DashboardStats = {
  total_users: number
  active_users_last_7_days: number
  new_users_this_month: number
  credits_used_this_month: number
  active_conversations: number
  platform_breakdown: Record<string, number>
  recent_activity: AuditEntry[]
}

type AdminUser = {
  uid: string
  name: string | null
  email: string | null
  avatar_url: string | null
  role: string
  status: string
  created_at: string | null
  last_login_at: string | null
  credit_balance?: { balance: number; plan: string } | null
}

type AuditEntry = {
  id: string
  admin_id: string
  action: string
  target_user_id: string | null
  details: Record<string, unknown> | null
  created_at: string | null
}

/* ─── Sub-tabs ───────────────────────────────────────────────────────── */

const ADMIN_TABS = ['Dashboard', 'Users', 'Agent Config', 'Messaging', 'Emailing', 'Audit Log'] as const
type AdminTab = (typeof ADMIN_TABS)[number]

/* ─── Helpers ────────────────────────────────────────────────────────── */

function StatCard({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div className='rounded-xl border border-[#2a2a2a] bg-[#111] p-4'>
      <p className='text-xs text-zinc-500'>{label}</p>
      <p className='mt-1 text-2xl font-bold text-white'>{value}</p>
      {sub && <p className='mt-0.5 text-[11px] text-zinc-600'>{sub}</p>}
    </div>
  )
}

const ROLE_COLORS: Record<string, string> = {
  superadmin: 'bg-red-500/10 text-red-300 border-red-500/20',
  admin: 'bg-blue-500/10 text-blue-300 border-blue-500/20',
  user: 'bg-zinc-700/50 text-zinc-400 border-zinc-700',
}

const STATUS_COLORS: Record<string, string> = {
  active: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  suspended: 'bg-red-500/10 text-red-400 border-red-500/20',
  pending: 'bg-amber-500/10 text-amber-300 border-amber-500/20',
}

/* ─── Dashboard Tab ──────────────────────────────────────────────────── */

function DashboardTab() {
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [showPaymentSettings, setShowPaymentSettings] = useState(false)
  const toast = useToast()

  useEffect(() => {
    void (async () => {
      try {
        const res = await fetch(apiUrl('/api/admin/dashboard/'), { credentials: 'include' })
        if (!res.ok) throw new Error('Failed to load dashboard')
        const data = (await res.json()) as DashboardStats
        setStats(data)
      } catch {
        toast.error('Failed to load dashboard stats')
      } finally {
        setLoading(false)
      }
    })()
  }, [toast])

  if (loading) {
    return (
      <div className='flex items-center justify-center py-12'>
        <LuLoader className='h-6 w-6 animate-spin text-zinc-500' />
      </div>
    )
  }
  if (!stats) return <p className='text-xs text-red-400'>Failed to load dashboard.</p>

  return (
    <div className='space-y-6'>
      <div>
        <h2 className='text-base font-semibold text-white'>Overview</h2>
        <p className='text-xs text-zinc-500'>Platform-wide statistics</p>
      </div>

      {/* KPI grid */}
      <div className='grid grid-cols-2 gap-3 lg:grid-cols-3'>
        <StatCard label='Total Users' value={stats.total_users} />
        <StatCard label='Active (last 7 days)' value={stats.active_users_last_7_days} />
        <StatCard label='New This Month' value={stats.new_users_this_month} />
        <StatCard label='Credits Used (month)' value={stats.credits_used_this_month.toLocaleString()} />
        <StatCard label='Active Conversations' value={stats.active_conversations} />
        <StatCard
          label='Platforms'
          value={Object.keys(stats.platform_breakdown).length}
          sub={Object.entries(stats.platform_breakdown)
            .map(([k, v]) => `${k}: ${v}`)
            .join(' · ')}
        />
      </div>

      {/* Recent activity */}
      {stats.recent_activity.length > 0 && (
        <div>
          <h3 className='mb-3 text-sm font-medium text-zinc-300'>Recent Admin Activity</h3>
          <div className='space-y-2'>
            {stats.recent_activity.map((entry) => (
              <div key={entry.id} className='flex items-start gap-3 rounded-lg border border-[#2a2a2a] bg-[#111] px-3 py-2.5'>
                <div className='mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-blue-500/10 text-blue-400'>
                  {Icons.settings({ className: 'h-3 w-3' })}
                </div>
                <div className='min-w-0'>
                  <p className='text-xs font-medium text-zinc-200'>{entry.action.replace(/_/g, ' ')}</p>
                  {entry.target_user_id && (
                    <p className='text-[11px] text-zinc-500'>Target: {entry.target_user_id}</p>
                  )}
                  {entry.created_at && (
                    <p className='text-[11px] text-zinc-600'>{new Date(entry.created_at).toLocaleString()}</p>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Payment Methods settings card */}
      <div>
        <h3 className='mb-3 text-sm font-medium text-zinc-300'>Configuration</h3>
        <div
          className='flex cursor-pointer items-center gap-4 rounded-xl border border-[#2a2a2a] bg-[#111] px-4 py-4 transition hover:border-white/16 hover:bg-white/4'
          onClick={() => setShowPaymentSettings(true)}
          role='button'
          tabIndex={0}
          onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') setShowPaymentSettings(true) }}
        >
          <div className='flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-cyan-500/10 text-cyan-400'>
            {Icons.settings({ className: 'h-4 w-4' })}
          </div>
          <div className='min-w-0 flex-1'>
            <p className='text-sm font-medium text-white'>Payment Methods</p>
            <p className='text-[12px] text-zinc-500'>Enable or disable Stripe and Coinbase Commerce</p>
          </div>
          {Icons.chevronRight({ className: 'h-4 w-4 text-zinc-600' })}
        </div>
      </div>

      {showPaymentSettings && (
        <PaymentSettingsModal onClose={() => setShowPaymentSettings(false)} />
      )}
    </div>
  )
}

/* ─── Users Tab ──────────────────────────────────────────────────────── */

function UsersTab() {
  const [users, setUsers] = useState<AdminUser[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [roleFilter, setRoleFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [page, setPage] = useState(0)
  const [selected, setSelected] = useState<AdminUser | null>(null)
  const [creditAdjust, setCreditAdjust] = useState('')
  const [creditNote, setCreditNote] = useState('')
  const [actionLoading, setActionLoading] = useState(false)
  const toast = useToast()
  const { startImpersonation } = useImpersonation()

  const PAGE_SIZE = 20

  const loadUsers = useCallback(async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(page * PAGE_SIZE) })
      if (search) params.set('search', search)
      if (roleFilter) params.set('role', roleFilter)
      if (statusFilter) params.set('status', statusFilter)
      const res = await fetch(apiUrl(`/api/admin/users/?${params}`), { credentials: 'include' })
      if (!res.ok) throw new Error('Failed to load users')
      const data = (await res.json()) as { users: AdminUser[]; total: number }
      setUsers(data.users ?? [])
      setTotal(data.total ?? 0)
    } catch {
      toast.error('Failed to load users')
    } finally {
      setLoading(false)
    }
  }, [search, roleFilter, statusFilter, page, toast])

  useEffect(() => { void loadUsers() }, [loadUsers])

  const doAction = async (path: string, method = 'POST', body?: Record<string, unknown>) => {
    setActionLoading(true)
    try {
      const res = await fetch(apiUrl(path), {
        method,
        headers: body ? { 'Content-Type': 'application/json' } : undefined,
        credentials: 'include',
        body: body ? JSON.stringify(body) : undefined,
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({})) as Record<string, unknown>
        throw new Error((err.detail as string) ?? 'Action failed')
      }
      return (await res.json()) as Record<string, unknown>
    } finally {
      setActionLoading(false)
    }
  }

  const changeRole = async (uid: string, role: string) => {
    try {
      await doAction(`/api/admin/users/${uid}/role`, 'PUT', { role })
      toast.success(`Role updated to ${role}`)
      void loadUsers()
      if (selected?.uid === uid) setSelected((prev) => prev ? { ...prev, role } : prev)
    } catch (e) { toast.error(String(e)) }
  }

  const suspend = async (uid: string) => {
    try {
      await doAction(`/api/admin/users/${uid}/suspend`)
      toast.success('User suspended')
      void loadUsers()
      if (selected?.uid === uid) setSelected((prev) => prev ? { ...prev, status: 'suspended' } : prev)
    } catch (e) { toast.error(String(e)) }
  }

  const reinstate = async (uid: string) => {
    try {
      await doAction(`/api/admin/users/${uid}/reinstate`)
      toast.success('User reinstated')
      void loadUsers()
      if (selected?.uid === uid) setSelected((prev) => prev ? { ...prev, status: 'active' } : prev)
    } catch (e) { toast.error(String(e)) }
  }

  const adjustCredit = async (uid: string) => {
    const amount = parseFloat(creditAdjust)
    if (isNaN(amount)) { toast.error('Enter a valid number'); return }
    try {
      await doAction(`/api/admin/users/${uid}/credit-adjustment`, 'POST', {
        amount,
        reason: creditNote || 'Admin adjustment',
      })
      toast.success(`Credits adjusted by ${amount}`)
      setCreditAdjust('')
      setCreditNote('')
      void loadUsers()
    } catch (e) { toast.error(String(e)) }
  }

  const impersonate = async (uid: string, email: string | null) => {
    const confirmed = window.confirm(`You will switch to ${email ?? uid}'s account. All actions will be logged. Continue?`)
    if (!confirmed) return

    try {
      const ok = await startImpersonation(uid)
      if (!ok) throw new Error('Impersonation failed')
      toast.success('Impersonation started')
      window.location.href = '/app'
    } catch (e) { toast.error((e as Error).message) }
  }

  /* ── User detail drawer ── */
  if (selected) {
    return (
      <div className='flex h-full flex-col'>
        <div className='mb-4 flex items-center gap-3 border-b border-[#2a2a2a] pb-4'>
          <button
            type='button'
            onClick={() => setSelected(null)}
            className='flex items-center gap-1.5 text-xs text-zinc-400 hover:text-zinc-200'
          >
            {Icons.back({ className: 'h-3.5 w-3.5' })}
            <span>All users</span>
          </button>
        </div>

        <div className='flex items-center gap-3 mb-5'>
          {selected.avatar_url ? (
            <img src={selected.avatar_url} alt='' className='h-10 w-10 rounded-full' />
          ) : (
            <span className='flex h-10 w-10 items-center justify-center rounded-full bg-zinc-700 text-sm font-bold text-zinc-200'>
              {(selected.name?.[0] || selected.email?.[0] || '?').toUpperCase()}
            </span>
          )}
          <div>
            <p className='text-sm font-semibold text-white'>{selected.name || 'No name'}</p>
            <p className='text-xs text-zinc-500'>{selected.email}</p>
          </div>
          <div className='ml-auto flex items-center gap-2'>
            <span className={`rounded-full border px-2 py-0.5 text-[10px] ${ROLE_COLORS[selected.role] ?? ROLE_COLORS.user}`}>
              {selected.role}
            </span>
            <span className={`rounded-full border px-2 py-0.5 text-[10px] ${STATUS_COLORS[selected.status] ?? STATUS_COLORS.active}`}>
              {selected.status}
            </span>
          </div>
        </div>

        <div className='grid grid-cols-2 gap-3 mb-5 text-xs'>
          <div className='rounded-lg border border-[#2a2a2a] bg-[#111] p-3'>
            <p className='text-zinc-500'>UID</p>
            <p className='mt-0.5 font-mono text-[11px] text-zinc-300 break-all'>{selected.uid}</p>
          </div>
          <div className='rounded-lg border border-[#2a2a2a] bg-[#111] p-3'>
            <p className='text-zinc-500'>Joined</p>
            <p className='mt-0.5 text-zinc-300'>{selected.created_at ? new Date(selected.created_at).toLocaleDateString() : '—'}</p>
          </div>
          <div className='rounded-lg border border-[#2a2a2a] bg-[#111] p-3'>
            <p className='text-zinc-500'>Last login</p>
            <p className='mt-0.5 text-zinc-300'>{selected.last_login_at ? new Date(selected.last_login_at).toLocaleString() : '—'}</p>
          </div>
          <div className='rounded-lg border border-[#2a2a2a] bg-[#111] p-3'>
            <p className='text-zinc-500'>Credits</p>
            <p className='mt-0.5 text-zinc-300'>{selected.credit_balance?.balance?.toLocaleString() ?? '—'}</p>
            {selected.credit_balance?.plan && <p className='text-[11px] text-zinc-600'>{selected.credit_balance.plan} plan</p>}
          </div>
        </div>

        {/* Actions */}
        <div className='space-y-3'>
          {/* Role */}
          <div className='rounded-xl border border-[#2a2a2a] bg-[#0f0f0f] p-4'>
            <p className='mb-2 text-xs font-medium text-zinc-300'>Change Role</p>
            <div className='flex gap-2'>
              {['user', 'admin', 'superadmin'].map((r) => (
                <button
                  key={r}
                  type='button'
                  onClick={() => changeRole(selected.uid, r)}
                  disabled={actionLoading || selected.role === r}
                  className={`rounded-lg border px-3 py-1.5 text-xs transition disabled:opacity-50 ${
                    selected.role === r
                      ? 'border-blue-500/50 bg-blue-600/20 text-blue-300'
                      : 'border-[#2a2a2a] text-zinc-400 hover:bg-zinc-800'
                  }`}
                >
                  {r}
                </button>
              ))}
            </div>
          </div>

          {/* Suspend / Reinstate */}
          <div className='rounded-xl border border-[#2a2a2a] bg-[#0f0f0f] p-4'>
            <p className='mb-2 text-xs font-medium text-zinc-300'>Account Status</p>
            <div className='flex gap-2'>
              <button
                type='button'
                onClick={() => suspend(selected.uid)}
                disabled={actionLoading || selected.status === 'suspended'}
                className='rounded-lg border border-red-500/30 px-3 py-1.5 text-xs text-red-400 hover:bg-red-500/10 disabled:opacity-40'
              >
                Suspend
              </button>
              <button
                type='button'
                onClick={() => reinstate(selected.uid)}
                disabled={actionLoading || selected.status === 'active'}
                className='rounded-lg border border-emerald-500/30 px-3 py-1.5 text-xs text-emerald-400 hover:bg-emerald-500/10 disabled:opacity-40'
              >
                Reinstate
              </button>
              <button
                type='button'
                onClick={() => impersonate(selected.uid, selected.email)}
                disabled={actionLoading}
                className='ml-auto flex items-center gap-1.5 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-1.5 text-xs text-amber-300 hover:bg-amber-500/20 disabled:opacity-40'
              >
                <LuEye className='h-3.5 w-3.5' />
                View as User
              </button>
            </div>
          </div>

          {/* Credit adjustment */}
          <div className='rounded-xl border border-[#2a2a2a] bg-[#0f0f0f] p-4'>
            <p className='mb-1 text-xs font-medium text-zinc-300'>Add / Adjust Credits</p>
            <p className='mb-3 text-[11px] text-zinc-600'>Positive number adds credits, negative deducts. E.g. <span className='text-zinc-500'>5000</span> adds 5,000 credits.</p>
            <div className='flex gap-2'>
              <input
                type='number'
                value={creditAdjust}
                onChange={(e) => setCreditAdjust(e.target.value)}
                placeholder='e.g. 5000 or -100'
                className='w-32 rounded-lg border border-[#2a2a2a] bg-[#111] px-2 py-1.5 text-xs text-zinc-100 placeholder-zinc-600 outline-none focus:border-blue-500/60'
              />
              <input
                type='text'
                value={creditNote}
                onChange={(e) => setCreditNote(e.target.value)}
                placeholder='Reason (optional)'
                className='flex-1 rounded-lg border border-[#2a2a2a] bg-[#111] px-2 py-1.5 text-xs text-zinc-100 placeholder-zinc-600 outline-none focus:border-blue-500/60'
              />
              <button
                type='button'
                onClick={() => adjustCredit(selected.uid)}
                disabled={actionLoading || !creditAdjust}
                className='rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-medium hover:bg-blue-500 disabled:opacity-40'
              >
                Apply
              </button>
            </div>
          </div>
        </div>
      </div>
    )
  }

  /* ── User list ── */
  const totalPages = Math.ceil(total / PAGE_SIZE)

  return (
    <div className='space-y-4'>
      <div className='flex flex-wrap items-center gap-2'>
        <input
          type='search'
          value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(0) }}
          placeholder='Search by name or email…'
          className='flex-1 min-w-[180px] rounded-lg border border-[#2a2a2a] bg-[#111] px-3 py-1.5 text-xs text-zinc-100 placeholder-zinc-600 outline-none focus:border-blue-500/60'
        />
        <select
          value={roleFilter}
          onChange={(e) => { setRoleFilter(e.target.value); setPage(0) }}
          className='rounded-lg border border-[#2a2a2a] bg-[#111] px-2 py-1.5 text-xs text-zinc-300 outline-none'
        >
          <option value=''>All roles</option>
          <option value='user'>User</option>
          <option value='admin'>Admin</option>
          <option value='superadmin'>Superadmin</option>
        </select>
        <select
          value={statusFilter}
          onChange={(e) => { setStatusFilter(e.target.value); setPage(0) }}
          className='rounded-lg border border-[#2a2a2a] bg-[#111] px-2 py-1.5 text-xs text-zinc-300 outline-none'
        >
          <option value=''>All statuses</option>
          <option value='active'>Active</option>
          <option value='suspended'>Suspended</option>
          <option value='pending'>Pending</option>
        </select>
        <span className='text-xs text-zinc-600'>{total} total</span>
      </div>

      {loading && (
        <div className='flex items-center justify-center py-12'>
          <LuLoader className='h-6 w-6 animate-spin text-zinc-500' />
        </div>
      )}

      {!loading && users.length === 0 && (
        <div className='flex flex-col items-center justify-center rounded-xl border border-[#2a2a2a] bg-[#111] p-8 text-center'>
          <LuSearch className='mb-2 h-8 w-8 text-zinc-600' />
          <p className='text-sm text-zinc-500'>No results found</p>
        </div>
      )}

      <div className='overflow-x-auto rounded-xl border border-[#2a2a2a]'>
        <table className='w-full text-xs'>
          <thead>
            <tr className='border-b border-[#2a2a2a] bg-[#0f0f0f] text-left text-zinc-500'>
              <th className='px-3 py-2.5 font-medium'>User</th>
              <th className='px-3 py-2.5 font-medium'>Role</th>
              <th className='px-3 py-2.5 font-medium'>Status</th>
              <th className='px-3 py-2.5 font-medium'>Joined</th>
              <th className='px-3 py-2.5 font-medium'>Last Login</th>
              <th className='px-3 py-2.5 font-medium text-right'>Actions</th>
            </tr>
          </thead>
          <tbody className='divide-y divide-[#1e1e1e]'>
            {users.map((u) => (
              <tr
                key={u.uid}
                onClick={() => setSelected(u)}
                className='cursor-pointer bg-[#111] transition hover:bg-zinc-900'
              >
                <td className='px-3 py-2.5'>
                  <div className='flex items-center gap-2'>
                    {u.avatar_url ? (
                      <img src={u.avatar_url} alt='' className='h-6 w-6 rounded-full' />
                    ) : (
                      <span className='flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-zinc-700 text-[10px] font-bold text-zinc-300'>
                        {(u.name?.[0] || u.email?.[0] || '?').toUpperCase()}
                      </span>
                    )}
                    <div className='min-w-0'>
                      <p className='font-medium text-zinc-100 truncate'>{u.name || '—'}</p>
                      <p className='text-zinc-500 truncate'>{u.email}</p>
                    </div>
                  </div>
                </td>
                <td className='px-3 py-2.5'>
                  <span className={`rounded-full border px-2 py-0.5 ${ROLE_COLORS[u.role] ?? ROLE_COLORS.user}`}>
                    {u.role}
                  </span>
                </td>
                <td className='px-3 py-2.5'>
                  <span className={`rounded-full border px-2 py-0.5 ${STATUS_COLORS[u.status] ?? STATUS_COLORS.active}`}>
                    {u.status}
                  </span>
                </td>
                <td className='px-3 py-2.5 text-zinc-500'>
                  {u.created_at ? new Date(u.created_at).toLocaleDateString() : '—'}
                </td>
                <td className='px-3 py-2.5 text-zinc-500'>
                  {u.last_login_at ? new Date(u.last_login_at).toLocaleDateString() : '—'}
                </td>
                <td className='px-3 py-2.5 text-right'>
                  <button
                    type='button'
                    onClick={(e) => {
                      e.stopPropagation()
                      void impersonate(u.uid, u.email)
                    }}
                    className='rounded p-1 text-zinc-400 hover:bg-zinc-800 hover:text-amber-300'
                    title='View as user'
                  >
                    <LuEye className='h-4 w-4' />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className='flex items-center justify-between text-xs text-zinc-500'>
          <span>Page {page + 1} of {totalPages}</span>
          <div className='flex gap-2'>
            <button
              type='button'
              disabled={page === 0}
              onClick={() => setPage((p) => p - 1)}
              className='rounded border border-[#2a2a2a] px-3 py-1 hover:bg-zinc-800 disabled:opacity-40'
            >
              Prev
            </button>
            <button
              type='button'
              disabled={page >= totalPages - 1}
              onClick={() => setPage((p) => p + 1)}
              className='rounded border border-[#2a2a2a] px-3 py-1 hover:bg-zinc-800 disabled:opacity-40'
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

/* ─── Agent Config Tab ───────────────────────────────────────────────── */

function AgentConfigTab() {
  const [instruction, setInstruction] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const toast = useToast()

  useEffect(() => {
    fetch(apiUrl('/api/admin/platform-settings'), { credentials: 'include' })
      .then((r) => r.json())
      .then((data) => {
        setInstruction(data.global_system_instruction ?? '')
        setLoading(false)
      })
      .catch(() => {
        toast.error('Failed to load platform settings')
        setLoading(false)
      })
  }, [toast])

  const handleSave = async () => {
    setSaving(true)
    setSaved(false)
    try {
      const r = await fetch(apiUrl('/api/admin/platform-settings'), {
        method: 'PATCH',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ global_system_instruction: instruction }),
      })
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      setSaved(true)
      toast.success('Global system instruction saved')
    } catch {
      toast.error('Save failed')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className='flex items-center justify-center py-16'>
        <LuLoader className='h-5 w-5 animate-spin text-zinc-400' />
      </div>
    )
  }

  return (
    <div className='max-w-2xl space-y-6'>
      <div>
        <h2 className='text-base font-semibold text-white'>Aegis Global System Instructions</h2>
        <p className='mt-1 text-xs text-zinc-400'>
          This instruction is injected at the top of every agent system prompt on every session,
          for every user. It is authoritative — users cannot see or override it. Use it to enforce
          platform-wide behavior, safety guardrails, brand voice, or restrictions.
        </p>
      </div>

      <div className='rounded-xl border border-amber-500/20 bg-amber-500/5 p-4'>
        <p className='text-xs font-medium text-amber-300'>Admin-only</p>
        <p className='mt-1 text-xs text-zinc-400'>
          Only admins can view or edit this. Users see a note in their Agent tab that global
          operator instructions apply, but they cannot read the content.
        </p>
      </div>

      <div className='space-y-2'>
        <label htmlFor='global-instruction' className='text-xs font-medium text-zinc-300'>
          Global instruction
        </label>
        <textarea
          id='global-instruction'
          value={instruction}
          onChange={(e) => { setInstruction(e.target.value); setSaved(false) }}
          rows={10}
          placeholder='e.g. You are operating as Aegis on the Acme Corp platform. Always respond in formal English. Never discuss competitor products. Route any billing questions to support@acme.com.'
          className='w-full rounded-lg border border-[#2a2a2a] bg-[#111] p-3 text-sm text-zinc-100 placeholder:text-zinc-600 focus:border-zinc-600 focus:outline-none'
        />
        <p className='text-xs text-zinc-500'>
          Leave blank to use only the built-in Aegis identity and the per-user runtime instructions.
        </p>
      </div>

      <button
        type='button'
        onClick={handleSave}
        disabled={saving}
        className='rounded-lg bg-zinc-700 px-4 py-2 text-sm font-medium text-white transition hover:bg-zinc-600 disabled:opacity-50'
      >
        {saving ? 'Saving...' : saved ? 'Saved' : 'Save instruction'}
      </button>
    </div>
  )
}

/* ─── Audit Log Tab ──────────────────────────────────────────────────── */

function AuditLogTab() {
  const [entries, setEntries] = useState<AuditEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(0)
  const [total, setTotal] = useState(0)
  const toast = useToast()
  const PAGE_SIZE = 30

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(page * PAGE_SIZE) })
      const res = await fetch(apiUrl(`/api/admin/audit/?${params}`), { credentials: 'include' })
      if (!res.ok) throw new Error('Failed to load audit log')
      const data = (await res.json()) as { entries: AuditEntry[]; total: number }
      setEntries(data.entries ?? [])
      setTotal(data.total ?? 0)
    } catch {
      toast.error('Failed to load audit log')
    } finally {
      setLoading(false)
    }
  }, [page, toast])

  useEffect(() => { void load() }, [load])

  const totalPages = Math.ceil(total / PAGE_SIZE)

  return (
    <div className='space-y-4'>
      <div>
        <h2 className='text-base font-semibold text-white'>Audit Log</h2>
        <p className='text-xs text-zinc-500'>All admin actions recorded in order</p>
      </div>

      {loading && (
        <div className='flex items-center justify-center py-12'>
          <LuLoader className='h-6 w-6 animate-spin text-zinc-500' />
        </div>
      )}

      {!loading && entries.length === 0 && (
        <div className='flex flex-col items-center justify-center rounded-xl border border-[#2a2a2a] bg-[#111] p-8 text-center'>
          <LuSearch className='mb-2 h-8 w-8 text-zinc-600' />
          <p className='text-sm text-zinc-500'>No results found</p>
        </div>
      )}

      <div className='space-y-1.5'>
        {entries.map((e) => (
          <div key={e.id} className='flex items-start gap-3 rounded-lg border border-[#2a2a2a] bg-[#111] px-3 py-2.5 text-xs'>
            <div className='mt-0.5 h-1.5 w-1.5 shrink-0 rounded-full bg-blue-400 mt-1.5' />
            <div className='min-w-0 flex-1'>
              <div className='flex items-center gap-2'>
                <span className='font-medium text-zinc-200'>{e.action.replace(/_/g, ' ')}</span>
                {e.target_user_id && (
                  <span className='text-zinc-500'>→ {e.target_user_id.slice(0, 8)}…</span>
                )}
              </div>
              {e.details && Object.keys(e.details).length > 0 && (
                <p className='mt-0.5 text-zinc-600 truncate'>
                  {Object.entries(e.details).map(([k, v]) => `${k}: ${String(v)}`).join(' · ')}
                </p>
              )}
            </div>
            <span className='shrink-0 text-zinc-600'>{e.created_at ? new Date(e.created_at).toLocaleString() : '—'}</span>
          </div>
        ))}
      </div>

      {totalPages > 1 && (
        <div className='flex items-center justify-between text-xs text-zinc-500'>
          <span>Page {page + 1} of {totalPages}</span>
          <div className='flex gap-2'>
            <button type='button' disabled={page === 0} onClick={() => setPage((p) => p - 1)} className='rounded border border-[#2a2a2a] px-3 py-1 hover:bg-zinc-800 disabled:opacity-40'>Prev</button>
            <button type='button' disabled={page >= totalPages - 1} onClick={() => setPage((p) => p + 1)} className='rounded border border-[#2a2a2a] px-3 py-1 hover:bg-zinc-800 disabled:opacity-40'>Next</button>
          </div>
        </div>
      )}
    </div>
  )
}

/* ─── Main AdminPanel ────────────────────────────────────────────────── */

export function AdminPanel() {
  const [activeTab, setActiveTab] = useState<AdminTab>('Dashboard')

  return (
    <div className='flex h-full min-w-0 flex-col gap-4'>
      {/* Header */}
      <div className='flex items-center gap-2 border-b border-[#2a2a2a] pb-4'>
        <div className='flex h-7 w-7 items-center justify-center rounded-lg bg-red-500/10'>
          {Icons.settings({ className: 'h-4 w-4 text-red-400' })}
        </div>
        <div>
          <h2 className='text-sm font-semibold text-white'>Admin Panel</h2>
          <p className='text-[11px] text-zinc-500'>Chronos AI · Platform management</p>
        </div>
      </div>

      {/* Sub-tab nav — horizontally scrollable on mobile */}
      <div className='w-full overflow-x-auto scrollbar-none rounded-lg border border-[#2a2a2a] bg-[#0f0f0f] p-1'>
        <div className='flex w-max gap-1'>
          {ADMIN_TABS.map((tab) => (
            <button
              key={tab}
              type='button'
              onClick={() => setActiveTab(tab)}
              className={`shrink-0 rounded-md px-3 py-1.5 text-xs font-medium whitespace-nowrap transition ${
                activeTab === tab ? 'bg-[#1e1e1e] text-zinc-100 shadow' : 'text-zinc-500 hover:text-zinc-300'
              }`}
            >
              {tab}
            </button>
          ))}
        </div>
      </div>

      {/* Tab content */}
      <div className='min-h-0 flex-1 overflow-y-auto'>
        {activeTab === 'Dashboard' && <DashboardTab />}
        {activeTab === 'Users' && <UsersTab />}
        {activeTab === 'Agent Config' && <AgentConfigTab />}
        {activeTab === 'Messaging' && <AdminMessaging />}
        {activeTab === 'Emailing' && <AdminEmailing />}
        {activeTab === 'Audit Log' && <AuditLogTab />}
      </div>
    </div>
  )
}
