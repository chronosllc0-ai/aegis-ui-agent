import { useEffect, useMemo, useState } from 'react'
import { apiRequest } from '../../lib/api'
import { ReviewQueue } from '../skills-hub/ReviewQueue'
import { SubmissionForm } from '../skills-hub/SubmissionForm'
import { SubmissionStatusTimeline } from '../skills-hub/SubmissionStatusTimeline'
import type { HubSubmission } from '../skills-hub/types'
import { useSettingsContext } from '../../context/useSettingsContext'
import { useSkills, type AdminSkillsPolicy, type InstalledSkill } from '../../hooks/useSkills'
import { useToast } from '../../hooks/useToast'

type SkillsTabProps = {
  role?: string
}

function formatDate(value?: string): string {
  if (!value) return 'Unknown'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Unknown'
  return date.toLocaleString()
}

export function SkillsTab({ role }: SkillsTabProps) {
  const isAdmin = role === 'admin' || role === 'superadmin'
  const [activeSegment, setActiveSegment] = useState<'my_skills' | 'admin_controls'>('my_skills')
  const toast = useToast()
  const { patchSettings } = useSettingsContext()
  const {
    installed,
    setInstalled,
    loadingInstalled,
    toggleSkill,
    uninstallSkill,
    refreshInstalled,
    policy,
    loadingPolicy,
    savePolicy,
  } = useSkills(isAdmin)

  const [savingPolicy, setSavingPolicy] = useState(false)
  const [expandedSkillId, setExpandedSkillId] = useState<string | null>(null)
  const [activeSubmission, setActiveSubmission] = useState<HubSubmission | null>(null)
  const [allowedTransitions, setAllowedTransitions] = useState<string[]>([])
  const [marketplaceSkills, setMarketplaceSkills] = useState<Array<{ id: string; name: string; slug: string; description: string; risk_label?: string }>>([])
  const [marketplaceError, setMarketplaceError] = useState<string>('')
  const [allowBlockQuery, setAllowBlockQuery] = useState('')
  const [allowBlockRows, setAllowBlockRows] = useState<Array<{ skill_id: string; skill: string; version: string; risk: string; allowed: boolean; blocked: boolean; updated: string }>>([])
  const [auditRows, setAuditRows] = useState<Array<{ id: string; user: string; skill_id: string; action: string; reason: string; timestamp: string }>>([])
  const [auditPage, setAuditPage] = useState(1)
  const [auditTotal, setAuditTotal] = useState(0)
  const [auditFilters, setAuditFilters] = useState({ user: '', skill: '', action: '', date_from: '', date_to: '' })
  const [pendingConfirm, setPendingConfirm] = useState<{ action: 'block' | 'reset'; skillId: string; skillName: string } | null>(null)

  const enabledSkillIds = useMemo(() => installed.filter((skill) => skill.enabled).map((skill) => skill.skill_id), [installed])

  useEffect(() => {
    patchSettings({ enabledSkillIds })
  }, [enabledSkillIds, patchSettings])

  useEffect(() => {
    void apiRequest<{ skills?: Array<{ id: string; name: string; slug: string; description: string; risk_label?: string }> }>('/api/skills/hub')
      .then((data) => setMarketplaceSkills(data.skills ?? []))
  }, [])

  const refreshAllowBlock = async (query: string = allowBlockQuery) => {
    if (!isAdmin) return
    const params = new URLSearchParams()
    if (query.trim()) params.set('q', query.trim())
    const data = await apiRequest<{ items?: Array<{ skill_id: string; skill: string; version: string; risk: string; allowed: boolean; blocked: boolean; updated: string }> }>(
      `/api/admin/skills/allow-block${params.toString() ? `?${params.toString()}` : ''}`,
    )
    setAllowBlockRows(data.items ?? [])
  }

  const refreshAudit = async (page: number = auditPage) => {
    if (!isAdmin) return
    const params = new URLSearchParams({ page: String(page), page_size: '10' })
    if (auditFilters.user.trim()) params.set('user', auditFilters.user.trim())
    if (auditFilters.skill.trim()) params.set('skill', auditFilters.skill.trim())
    if (auditFilters.action.trim()) params.set('action', auditFilters.action.trim())
    if (auditFilters.date_from) params.set('date_from', auditFilters.date_from)
    if (auditFilters.date_to) params.set('date_to', auditFilters.date_to)
    const data = await apiRequest<{ items?: Array<{ id: string; user: string; skill_id: string; action: string; reason: string; timestamp: string }>; total?: number }>(
      `/api/admin/skills/install-audit?${params.toString()}`,
    )
    setAuditRows(data.items ?? [])
    setAuditTotal(data.total ?? 0)
  }

  useEffect(() => {
    if (!isAdmin) return
    void refreshAllowBlock()
    void refreshAudit(1)
  }, [isAdmin])

  const onToggleSkill = async (skill: InstalledSkill) => {
    const nextEnabled = !skill.enabled
    setInstalled((prev) => prev.map((item) => (item.skill_id === skill.skill_id ? { ...item, enabled: nextEnabled } : item)))
    try {
      await toggleSkill(skill.skill_id, nextEnabled)
    } catch (error) {
      setInstalled((prev) => prev.map((item) => (item.skill_id === skill.skill_id ? { ...item, enabled: skill.enabled } : item)))
      toast.error('Failed to update skill', error instanceof Error ? error.message : 'Please retry.')
    }
  }

  const onDeleteSkill = async (skillId: string) => {
    const previous = installed
    setInstalled((prev) => prev.filter((skill) => skill.skill_id !== skillId))
    try {
      await uninstallSkill(skillId)
      toast.success('Skill uninstalled')
    } catch (error) {
      setInstalled(previous)
      toast.error('Failed to uninstall skill', error instanceof Error ? error.message : 'Please retry.')
    }
  }

  const onInstallMarketplaceSkill = async (skillId: string) => {
    try {
      await apiRequest(`/api/skills/${encodeURIComponent(skillId)}/install`, { method: 'POST' })
      setMarketplaceError('')
      await refreshInstalled()
      toast.success('Skill installed')
    } catch (error) {
      setMarketplaceError(error instanceof Error ? error.message : 'Install blocked by policy')
      toast.error('Skill install blocked', error instanceof Error ? error.message : 'Install blocked by policy')
    }
  }

  const updatePolicy = async (partial: Partial<AdminSkillsPolicy>) => {
    const next = { ...policy, ...partial }
    setSavingPolicy(true)
    try {
      await savePolicy(next)
      toast.success('Policy updated')
    } catch (error) {
      toast.error('Failed to save policy', error instanceof Error ? error.message : 'Please retry.')
    } finally {
      setSavingPolicy(false)
    }
  }

  const onAllowBlockAction = async (skillId: string, action: 'allow' | 'block' | 'reset') => {
    await apiRequest(`/api/admin/skills/${encodeURIComponent(skillId)}/${action}`, { method: 'POST' })
    await refreshAllowBlock()
    toast.success(`Skill ${action}ed`)
  }


  const transitionSubmission = async (nextState: string) => {
    if (!activeSubmission) return
    const data = await apiRequest<{ submission: HubSubmission; allowed_transitions: string[] }>(`/api/skills/hub/submissions/${encodeURIComponent(activeSubmission.id)}/transition`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ next_state: nextState }),
    })
    setActiveSubmission(data.submission)
    setAllowedTransitions(data.allowed_transitions ?? [])
  }

  return (
    <div className='grid gap-4 lg:grid-cols-2'>
      <section className='rounded-xl border border-[#2a2a2a] bg-[#121212] p-2 lg:col-span-2'>
        <div className='inline-flex rounded-lg border border-[#2a2a2a] bg-[#0f0f0f] p-1'>
          <button
            type='button'
            className={`rounded-md px-3 py-1.5 text-xs ${activeSegment === 'my_skills' ? 'bg-cyan-500/20 text-cyan-200' : 'text-zinc-400'}`}
            onClick={() => setActiveSegment('my_skills')}
          >
            My Skills
          </button>
          {isAdmin ? (
            <button
              type='button'
              className={`rounded-md px-3 py-1.5 text-xs ${activeSegment === 'admin_controls' ? 'bg-cyan-500/20 text-cyan-200' : 'text-zinc-400'}`}
              onClick={() => setActiveSegment('admin_controls')}
            >
              Admin Controls
            </button>
          ) : null}
        </div>
      </section>

      {activeSegment === 'my_skills' ? (
        <>
      <section className='rounded-xl border border-[#2a2a2a] bg-[#121212] p-4'>
        <div className='mb-3 flex items-center justify-between'>
          <h3 className='text-sm font-semibold'>Installed skills</h3>
          <button type='button' className='rounded border border-[#2a2a2a] px-2 py-1 text-xs hover:bg-zinc-800' onClick={() => void refreshInstalled()}>
            Refresh
          </button>
        </div>
        {loadingInstalled ? (
          <p className='text-xs text-zinc-400'>Loading installed skills…</p>
        ) : installed.length === 0 ? (
          <p className='text-xs text-zinc-400'>No skills installed yet.</p>
        ) : (
          <div className='space-y-2'>
            {installed.map((skill) => (
              <article key={skill.skill_id} className='rounded-lg border border-[#2a2a2a] bg-[#171717] p-3'>
                <div className='flex items-start justify-between gap-2'>
                  <div>
                    <h4 className='text-sm font-medium text-zinc-100'>{skill.name}</h4>
                    <p className='text-[11px] text-zinc-500'>{skill.slug}</p>
                  </div>
                  <button
                    type='button'
                    onClick={() => void onToggleSkill(skill)}
                    className={`rounded-full border px-2.5 py-1 text-[11px] ${skill.enabled ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300' : 'border-[#2a2a2a] bg-[#1d1d1d] text-zinc-500'}`}
                  >
                    {skill.enabled ? 'Enabled' : 'Disabled'}
                  </button>
                </div>

                <div className='mt-2 flex flex-wrap gap-1.5 text-[10px]'>
                  <span className='rounded-full border border-[#333] px-2 py-0.5 text-zinc-300'>version: {skill.version_id.slice(0, 8)}</span>
                  <span className='rounded-full border border-[#333] px-2 py-0.5 text-zinc-300'>source: {skill.publish_target ?? 'hub'}</span>
                  <span className='rounded-full border border-[#333] px-2 py-0.5 text-zinc-300'>updated: {formatDate(skill.updated_at)}</span>
                  <span className='rounded-full border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-amber-300'>risk: {skill.risk_label ?? 'unknown'}</span>
                </div>

                <div className='mt-3 flex flex-wrap gap-2'>
                  <button type='button' onClick={() => setExpandedSkillId((prev) => (prev === skill.skill_id ? null : skill.skill_id))} className='rounded border border-cyan-500/40 px-2 py-1 text-xs text-cyan-300 hover:bg-cyan-500/10'>
                    Submit to Hub
                  </button>

                  <button type='button' onClick={() => void onDeleteSkill(skill.skill_id)} className='rounded border border-red-500/40 px-2 py-1 text-xs text-red-300 hover:bg-red-500/10'>
                    Uninstall
                  </button>
                </div>

                {expandedSkillId === skill.skill_id ? (
                  <div className='mt-2 space-y-2'>
                    <SubmissionForm
                      skillId={skill.skill_id}
                      slug={skill.slug}
                      title={skill.name}
                      onCreated={(submission) => {
                        setActiveSubmission(submission)
                        setAllowedTransitions(submission.current_state === 'draft' ? ['submitted'] : [])
                      }}
                    />
                    {activeSubmission && activeSubmission.skill_id === skill.skill_id ? (
                      <SubmissionStatusTimeline submission={activeSubmission} allowedTransitions={allowedTransitions} onTransition={(state) => void transitionSubmission(state)} />
                    ) : null}
                  </div>
                ) : null}
              </article>
            ))}
          </div>
        )}
      </section>

      <ReviewQueue isAdmin={isAdmin} />
      <section className='rounded-xl border border-[#2a2a2a] bg-[#121212] p-4 lg:col-span-2'>
        <h3 className='mb-3 text-sm font-semibold'>Marketplace</h3>
        {marketplaceError ? <p className='mb-2 text-xs text-red-300'>{marketplaceError}</p> : null}
        <div className='grid gap-2 md:grid-cols-2'>
          {marketplaceSkills.map((skill) => (
            <article key={skill.id} className='rounded-lg border border-[#2a2a2a] bg-[#171717] p-3'>
              <div className='flex items-center justify-between gap-2'>
                <div>
                  <h4 className='text-sm font-medium text-zinc-100'>{skill.name}</h4>
                  <p className='text-[11px] text-zinc-500'>{skill.slug}</p>
                </div>
                <span className='rounded-full border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-[10px] text-amber-300'>{skill.risk_label ?? 'scan_pending'}</span>
              </div>
              <p className='mt-2 line-clamp-2 text-xs text-zinc-400'>{skill.description || 'No description provided.'}</p>
              <button type='button' onClick={() => void onInstallMarketplaceSkill(skill.id)} className='mt-2 rounded border border-cyan-500/40 px-2 py-1 text-xs text-cyan-300 hover:bg-cyan-500/10'>
                Install
              </button>
            </article>
          ))}
        </div>
      </section>
        </>
      ) : null}

      {isAdmin && activeSegment === 'admin_controls' ? (
        <>
          <section className='rounded-xl border border-[#2a2a2a] bg-[#121212] p-4'>
            <h3 className='mb-3 text-sm font-semibold'>Policy Defaults</h3>
            {loadingPolicy ? (
              <p className='text-xs text-zinc-400'>Loading policy…</p>
            ) : (
              <div className='space-y-3'>
                <ToggleRow
                  label='Require approval before install'
                  value={policy.require_approval_before_install}
                  onToggle={(value) => void updatePolicy({ require_approval_before_install: value })}
                  disabled={savingPolicy}
                />
                <div className='space-y-1'>
                  <p className='text-xs font-medium text-zinc-300'>Default enabled skills for new users</p>
                  <div className='max-h-44 space-y-1 overflow-y-auto rounded border border-[#2a2a2a] bg-[#101010] p-2'>
                    {marketplaceSkills.map((skill) => {
                      const checked = policy.default_enabled_skill_ids.includes(skill.id)
                      return (
                        <label key={skill.id} className='flex items-center gap-2 text-xs text-zinc-300'>
                          <input
                            type='checkbox'
                            checked={checked}
                            onChange={(event) => {
                              const next = event.target.checked
                                ? [...policy.default_enabled_skill_ids, skill.id]
                                : policy.default_enabled_skill_ids.filter((entry) => entry !== skill.id)
                              void updatePolicy({ default_enabled_skill_ids: Array.from(new Set(next)) })
                            }}
                          />
                          <span>{skill.name}</span>
                        </label>
                      )
                    })}
                  </div>
                </div>
              </div>
            )}
          </section>

          <section className='rounded-xl border border-[#2a2a2a] bg-[#121212] p-4'>
            <div className='mb-3 flex items-center justify-between gap-2'>
              <h3 className='text-sm font-semibold'>Allow / Block List</h3>
              <input
                value={allowBlockQuery}
                onChange={(event) => setAllowBlockQuery(event.target.value)}
                placeholder='Search skills'
                className='rounded border border-[#2a2a2a] bg-[#101010] px-2 py-1 text-xs'
              />
              <button type='button' className='rounded border border-[#2a2a2a] px-2 py-1 text-xs' onClick={() => void refreshAllowBlock()}>
                Search
              </button>
            </div>
            <div className='overflow-x-auto'>
              <table className='w-full text-left text-xs'>
                <thead className='text-zinc-400'>
                  <tr>
                    <th className='pb-2'>Skill</th><th className='pb-2'>Version</th><th className='pb-2'>Risk</th><th className='pb-2'>Allowed</th><th className='pb-2'>Blocked</th><th className='pb-2'>Updated</th><th className='pb-2'>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {allowBlockRows.map((row) => (
                    <tr key={row.skill_id} className='border-t border-[#232323]'>
                      <td className='py-2'>{row.skill}</td>
                      <td>{row.version}</td>
                      <td>{row.risk}</td>
                      <td>{row.allowed ? 'Yes' : 'No'}</td>
                      <td>{row.blocked ? 'Yes' : 'No'}</td>
                      <td>{formatDate(row.updated)}</td>
                      <td className='space-x-1'>
                        <button type='button' className='rounded border border-emerald-500/40 px-1.5 py-0.5 text-emerald-300' onClick={() => void onAllowBlockAction(row.skill_id, 'allow')}>Allow</button>
                        <button type='button' className='rounded border border-red-500/40 px-1.5 py-0.5 text-red-300' onClick={() => setPendingConfirm({ action: 'block', skillId: row.skill_id, skillName: row.skill })}>Block</button>
                        <button type='button' className='rounded border border-zinc-500/40 px-1.5 py-0.5 text-zinc-300' onClick={() => setPendingConfirm({ action: 'reset', skillId: row.skill_id, skillName: row.skill })}>Reset</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className='rounded-xl border border-[#2a2a2a] bg-[#121212] p-4 lg:col-span-2'>
            <h3 className='mb-3 text-sm font-semibold'>Org Install Audit</h3>
            <div className='mb-3 grid gap-2 md:grid-cols-5'>
              <input placeholder='user' value={auditFilters.user} onChange={(event) => setAuditFilters((prev) => ({ ...prev, user: event.target.value }))} className='rounded border border-[#2a2a2a] bg-[#101010] px-2 py-1 text-xs' />
              <input placeholder='skill id' value={auditFilters.skill} onChange={(event) => setAuditFilters((prev) => ({ ...prev, skill: event.target.value }))} className='rounded border border-[#2a2a2a] bg-[#101010] px-2 py-1 text-xs' />
              <input placeholder='action' value={auditFilters.action} onChange={(event) => setAuditFilters((prev) => ({ ...prev, action: event.target.value }))} className='rounded border border-[#2a2a2a] bg-[#101010] px-2 py-1 text-xs' />
              <input type='datetime-local' value={auditFilters.date_from} onChange={(event) => setAuditFilters((prev) => ({ ...prev, date_from: event.target.value }))} className='rounded border border-[#2a2a2a] bg-[#101010] px-2 py-1 text-xs' />
              <input type='datetime-local' value={auditFilters.date_to} onChange={(event) => setAuditFilters((prev) => ({ ...prev, date_to: event.target.value }))} className='rounded border border-[#2a2a2a] bg-[#101010] px-2 py-1 text-xs' />
            </div>
            <button type='button' className='mb-3 rounded border border-[#2a2a2a] px-2 py-1 text-xs' onClick={() => { setAuditPage(1); void refreshAudit(1) }}>Apply filters</button>
            <div className='space-y-2'>
              {auditRows.map((row) => (
                <article key={row.id} className='rounded border border-[#2a2a2a] bg-[#171717] p-2 text-xs'>
                  <p className='text-zinc-200'>{row.action} • {row.skill_id}</p>
                  <p className='text-zinc-400'>{row.user} • {formatDate(row.timestamp)} • {row.reason || 'n/a'}</p>
                </article>
              ))}
            </div>
            <div className='mt-3 flex items-center justify-between text-xs'>
              <span>Page {auditPage} • {auditTotal} total</span>
              <div className='space-x-2'>
                <button type='button' disabled={auditPage <= 1} className='rounded border border-[#2a2a2a] px-2 py-1 disabled:opacity-40' onClick={() => { const next = Math.max(auditPage - 1, 1); setAuditPage(next); void refreshAudit(next) }}>Prev</button>
                <button type='button' disabled={auditPage * 10 >= auditTotal} className='rounded border border-[#2a2a2a] px-2 py-1 disabled:opacity-40' onClick={() => { const next = auditPage + 1; setAuditPage(next); void refreshAudit(next) }}>Next</button>
              </div>
            </div>
          </section>
        </>
      ) : null}

      {pendingConfirm ? (
        <div className='fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4'>
          <div className='w-full max-w-md rounded-xl border border-[#2a2a2a] bg-[#111] p-4'>
            <h4 className='text-sm font-semibold'>Confirm {pendingConfirm.action}</h4>
            <p className='mt-2 text-xs text-zinc-400'>Are you sure you want to {pendingConfirm.action} <span className='text-zinc-200'>{pendingConfirm.skillName}</span>?</p>
            <div className='mt-3 flex justify-end gap-2'>
              <button type='button' className='rounded border border-[#2a2a2a] px-2 py-1 text-xs' onClick={() => setPendingConfirm(null)}>Cancel</button>
              <button
                type='button'
                className='rounded border border-red-500/40 px-2 py-1 text-xs text-red-300'
                onClick={() => {
                  const pending = pendingConfirm
                  setPendingConfirm(null)
                  void onAllowBlockAction(pending.skillId, pending.action)
                }}
              >
                Confirm
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}

function ToggleRow({ label, value, onToggle, disabled }: { label: string; value: boolean; onToggle: (next: boolean) => void; disabled?: boolean }) {
  return (
    <button type='button' disabled={disabled} onClick={() => onToggle(!value)} className='flex w-full items-center justify-between rounded border border-[#2a2a2a] px-3 py-2 text-sm disabled:opacity-60'>
      <span>{label}</span>
      <span className={value ? 'text-emerald-300' : 'text-zinc-500'}>{value ? 'On' : 'Off'}</span>
    </button>
  )
}
