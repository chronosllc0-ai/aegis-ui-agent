import { useState } from 'react'
import { useToast } from '../../hooks/useToast'
import { useSkills, type AdminSkillsPolicy, type InstalledSkill } from '../../hooks/useSkills'

type SkillsTabProps = {
  authRole?: string
}

function formatDate(value?: string): string {
  if (!value) return 'Unknown'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return 'Unknown'
  return parsed.toLocaleString()
}

function Pill({ children }: { children: string }) {
  return <span className='rounded-full border border-[#2f2f2f] bg-[#151515] px-2 py-0.5 text-[10px] text-zinc-300'>{children}</span>
}

function SkillRow({
  skill,
  onToggle,
  onDelete,
}: {
  skill: InstalledSkill
  onToggle: (skill: InstalledSkill) => void
  onDelete: (skill: InstalledSkill) => void
}) {
  return (
    <div className='rounded-xl border border-[#2a2a2a] bg-[#121212] p-3'>
      <div className='flex items-start justify-between gap-3'>
        <div>
          <p className='text-sm font-semibold text-zinc-100'>{skill.name}</p>
          <p className='text-xs text-zinc-500'>{skill.slug}</p>
        </div>
        <button
          type='button'
          onClick={() => onDelete(skill)}
          className='rounded border border-red-500/30 px-2 py-1 text-xs text-red-300 hover:bg-red-500/10'
        >
          Uninstall
        </button>
      </div>
      <div className='mt-2 flex flex-wrap gap-1.5'>
        <Pill>{`version:${skill.version ?? 'n/a'}`}</Pill>
        <Pill>{`source:${skill.source ?? skill.publish_target ?? 'unknown'}`}</Pill>
        <Pill>{`updated:${formatDate(skill.updated_at)}`}</Pill>
        <Pill>{`risk:${skill.risk_label ?? 'unknown'}`}</Pill>
      </div>
      <button
        type='button'
        role='switch'
        aria-checked={skill.enabled}
        onClick={() => onToggle(skill)}
        className={`mt-3 rounded border px-3 py-1 text-xs ${
          skill.enabled ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300' : 'border-[#2f2f2f] text-zinc-400'
        }`}
      >
        {skill.enabled ? 'Enabled' : 'Disabled'}
      </button>
    </div>
  )
}

export function SkillsTab({ authRole }: SkillsTabProps) {
  const isAdmin = authRole === 'admin' || authRole === 'superadmin'
  const { installedSkills, loading, policy, toggleSkill, uninstallSkill, updatePolicy } = useSkills(isAdmin)
  const toast = useToast()
  const [defaultsInput, setDefaultsInput] = useState('')

  const handleToggle = async (skill: InstalledSkill) => {
    try {
      await toggleSkill(skill.skill_id, !skill.enabled)
    } catch (error) {
      toast.error('Skill toggle failed', error instanceof Error ? error.message : 'Unable to update skill state.')
    }
  }

  const handleDelete = async (skill: InstalledSkill) => {
    try {
      await uninstallSkill(skill.skill_id)
      toast.success('Skill uninstalled', `${skill.name} removed from your runtime.`)
    } catch (error) {
      toast.error('Uninstall failed', error instanceof Error ? error.message : 'Unable to remove skill.')
    }
  }

  const patchPolicy = async (partial: Partial<AdminSkillsPolicy>) => {
    try {
      await updatePolicy(partial)
    } catch (error) {
      toast.error('Policy update failed', error instanceof Error ? error.message : 'Could not save admin skill policy.')
    }
  }

  return (
    <div className='grid gap-4 lg:grid-cols-2'>
      <section className='space-y-3 rounded-2xl border border-[#2a2a2a] p-4'>
        <div>
          <h3 className='text-sm font-semibold'>Installed skills</h3>
          <p className='text-xs text-zinc-500'>Manage your installed runtime skills.</p>
        </div>
        {loading ? <p className='text-xs text-zinc-500'>Loading skills…</p> : null}
        {!loading && installedSkills.length === 0 ? <p className='text-xs text-zinc-500'>No skills installed yet.</p> : null}
        <div className='space-y-2'>
          {installedSkills.map((skill) => (
            <SkillRow key={skill.skill_id} skill={skill} onToggle={handleToggle} onDelete={handleDelete} />
          ))}
        </div>
      </section>

      {isAdmin && (
        <section className='space-y-3 rounded-2xl border border-violet-500/30 bg-violet-500/5 p-4'>
          <div>
            <h3 className='text-sm font-semibold text-violet-200'>Org skill policy</h3>
            <p className='text-xs text-zinc-400'>Admin-only governance controls for skills.</p>
          </div>

          <PolicyToggle
            label='Allow global skills'
            checked={policy.allow_global_skills}
            onClick={() => void patchPolicy({ allow_global_skills: !policy.allow_global_skills })}
          />
          <PolicyToggle
            label='Allow hub skills'
            checked={policy.allow_hub_skills}
            onClick={() => void patchPolicy({ allow_hub_skills: !policy.allow_hub_skills })}
          />
          <PolicyToggle
            label='Require approval before install'
            checked={policy.require_approval_before_install}
            onClick={() => void patchPolicy({ require_approval_before_install: !policy.require_approval_before_install })}
          />

          <div className='rounded border border-[#2a2a2a] p-3'>
            <p className='text-xs font-medium text-zinc-300'>Org default-enabled skill set</p>
            <p className='mt-1 text-[11px] text-zinc-500'>Comma-separated skill IDs. Unknown IDs are ignored.</p>
            <input
              value={defaultsInput}
              onChange={(event) => setDefaultsInput(event.target.value)}
              placeholder={policy.default_enabled_skill_ids.join(',')}
              className='mt-2 w-full rounded border border-[#2a2a2a] bg-[#111] px-2 py-1 text-xs'
            />
            <button
              type='button'
              onClick={() => {
                const ids = defaultsInput
                  .split(',')
                  .map((part) => part.trim())
                  .filter((part) => part)
                void patchPolicy({ default_enabled_skill_ids: ids })
              }}
              className='mt-2 rounded border border-violet-500/40 px-2 py-1 text-xs text-violet-200'
            >
              Save defaults
            </button>
          </div>
        </section>
      )}
    </div>
  )
}

function PolicyToggle({ label, checked, onClick }: { label: string; checked: boolean; onClick: () => void }) {
  return (
    <button type='button' onClick={onClick} className='flex w-full items-center justify-between rounded border border-[#2a2a2a] px-3 py-2 text-xs'>
      <span>{label}</span>
      <span className={checked ? 'text-emerald-300' : 'text-zinc-500'}>{checked ? 'On' : 'Off'}</span>
    </button>
  )
}
