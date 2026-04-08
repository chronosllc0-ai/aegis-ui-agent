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

  const enabledSkillIds = useMemo(() => installed.filter((skill) => skill.enabled).map((skill) => skill.skill_id), [installed])

  useEffect(() => {
    patchSettings({ enabledSkillIds })
  }, [enabledSkillIds, patchSettings])

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

      {isAdmin && (
        <section className='rounded-xl border border-[#2a2a2a] bg-[#121212] p-4'>
          <h3 className='mb-3 text-sm font-semibold'>Organization policy</h3>
          {loadingPolicy ? (
            <p className='text-xs text-zinc-400'>Loading policy…</p>
          ) : (
            <div className='space-y-3'>
              <ToggleRow
                label='Allow unreviewed installs'
                value={policy.allow_unreviewed_installs}
                onToggle={(value) => void updatePolicy({ allow_unreviewed_installs: value })}
                disabled={savingPolicy}
              />
              <ToggleRow
                label='Block high-risk skills'
                value={policy.block_high_risk_skills}
                onToggle={(value) => void updatePolicy({ block_high_risk_skills: value })}
                disabled={savingPolicy}
              />
              <ToggleRow
                label='Require approval before install'
                value={policy.require_approval_before_install}
                onToggle={(value) => void updatePolicy({ require_approval_before_install: value })}
                disabled={savingPolicy}
              />

              <div className='space-y-1'>
                <label htmlFor='org-default-enabled-skill-ids' className='text-xs font-medium text-zinc-300'>
                  Org default-enabled skill IDs
                </label>
                <textarea
                  id='org-default-enabled-skill-ids'
                  className='h-24 w-full rounded border border-[#2a2a2a] bg-[#111] p-2 text-xs'
                  value={policy.default_enabled_skill_ids.join('\n')}
                  onChange={(event) => void updatePolicy({ default_enabled_skill_ids: event.target.value.split('\n').map((line) => line.trim()).filter(Boolean) })}
                />
              </div>
            </div>
          )}
        </section>
      )}

      <ReviewQueue isAdmin={isAdmin} />
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
