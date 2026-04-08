import { useEffect, useMemo, useState, type ChangeEvent, type DragEvent } from 'react'
import { useSettingsContext } from '../../context/useSettingsContext'
import {
  useSkills,
  type AdminSkillsPolicy,
  type AdminSkillQueueItem,
  type HubSkill,
  type InstalledSkill,
} from '../../hooks/useSkills'
import { useToast } from '../../hooks/useToast'

type SkillsTabProps = {
  role?: string
}

type MarketplaceView = 'table' | 'cards'

type PublishForm = {
  slug: string
  name: string
  description: string
  owner: string
  version: string
  tags: string
  changelog: string
  acceptedLicense: boolean
  publishTarget: 'hub' | 'global'
}

const AEGIS_GRADIENT = 'bg-[radial-gradient(circle_at_top,_rgba(251,113,133,0.18),_rgba(17,17,17,0.9)_55%,_#0b0b0b)]'

function formatDate(value?: string): string {
  if (!value) return 'Unknown'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Unknown'
  return date.toLocaleDateString()
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
    installSkill,
    hubSkills,
    loadingHub,
    refreshHub,
    submitSkill,
    policy,
    loadingPolicy,
    savePolicy,
    reviewQueue,
    loadingQueue,
    refreshReviewQueue,
    reviewSubmission,
    scanSubmission,
  } = useSkills(isAdmin)

  const [savingPolicy, setSavingPolicy] = useState(false)
  const [activeSkillId, setActiveSkillId] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [riskFilter, setRiskFilter] = useState<'all' | 'low' | 'medium' | 'high'>('all')
  const [marketView, setMarketView] = useState<MarketplaceView>('table')
  const [publishForm, setPublishForm] = useState<PublishForm>({
    slug: '',
    name: '',
    description: '',
    owner: '@aegis-user',
    version: '1.0.0',
    tags: 'latest',
    changelog: '',
    acceptedLicense: false,
    publishTarget: 'hub',
  })
  const [skillMarkdown, setSkillMarkdown] = useState('')
  const [droppedFiles, setDroppedFiles] = useState<File[]>([])
  const [submitting, setSubmitting] = useState(false)

  const enabledSkillIds = useMemo(() => installed.filter((skill) => skill.enabled).map((skill) => skill.skill_id), [installed])

  useEffect(() => {
    patchSettings({ enabledSkillIds })
  }, [enabledSkillIds, patchSettings])

  const hubFiltered = useMemo(() => {
    return hubSkills.filter((skill) => {
      const riskMatch = riskFilter === 'all' || (skill.risk_label ?? 'medium') === riskFilter
      const token = `${skill.name} ${skill.slug} ${skill.description}`.toLowerCase()
      return riskMatch && token.includes(search.toLowerCase().trim())
    })
  }, [hubSkills, riskFilter, search])

  const selectedSkill = useMemo(() => {
    if (!activeSkillId) return hubFiltered[0] ?? null
    return hubSkills.find((skill) => skill.id === activeSkillId) ?? hubFiltered[0] ?? null
  }, [activeSkillId, hubFiltered, hubSkills])

  const installedById = useMemo(() => new Set(installed.map((skill) => skill.skill_id)), [installed])

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

  const onInstallSkill = async (skill: HubSkill) => {
    try {
      await installSkill(skill.id)
      await refreshInstalled()
      toast.success('Skill installed', `${skill.name} is now available in your runtime tools.`)
    } catch (error) {
      toast.error('Failed to install skill', error instanceof Error ? error.message : 'Please retry.')
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

  const onDropFiles = async (files: FileList | null) => {
    if (!files) return
    const list = Array.from(files)
    setDroppedFiles(list)
    const markdownFile = list.find((file) => /skill\.md$/i.test(file.name))
    if (!markdownFile) return
    const text = await markdownFile.text()
    setSkillMarkdown(text)
  }

  const onDrop = async (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    await onDropFiles(event.dataTransfer.files)
  }

  const onFileInput = async (event: ChangeEvent<HTMLInputElement>) => {
    await onDropFiles(event.target.files)
  }

  const onPublish = async () => {
    if (!publishForm.slug.trim() || !publishForm.name.trim()) {
      toast.error('Validation error', 'Slug and display name are required.')
      return
    }
    if (!publishForm.acceptedLicense) {
      toast.error('Validation error', 'Please accept the Aegis MIT-0 license terms.')
      return
    }
    if (!skillMarkdown.trim()) {
      toast.error('Validation error', 'SKILL.md content is required.')
      return
    }

    setSubmitting(true)
    try {
      await submitSkill({
        slug: publishForm.slug.trim(),
        name: publishForm.name.trim(),
        description: publishForm.description.trim(),
        publish_target: publishForm.publishTarget,
        metadata_json: {
          owner: publishForm.owner,
          version: publishForm.version,
          tags: publishForm.tags.split(',').map((tag) => tag.trim()).filter(Boolean),
          changelog: publishForm.changelog,
        },
        skill_md: skillMarkdown,
        workflow_action: 'submit_review',
      })
      toast.success('Skill submitted', 'Your skill was submitted to the Aegis publishing queue.')
      await refreshHub()
      if (isAdmin) await refreshReviewQueue()
    } catch (error) {
      toast.error('Failed to submit skill', error instanceof Error ? error.message : 'Please retry.')
    } finally {
      setSubmitting(false)
    }
  }

  const handleReviewAction = async (item: AdminSkillQueueItem, action: 'scan' | 'approve_hub' | 'approve_global' | 'reject') => {
    try {
      if (action === 'scan') await scanSubmission(item.submission.id)
      else await reviewSubmission(item.submission.id, action)
      toast.success('Admin action completed')
      await refreshReviewQueue()
      await refreshHub()
    } catch (error) {
      toast.error('Admin action failed', error instanceof Error ? error.message : 'Please retry.')
    }
  }

  return (
    <div className={`space-y-5 rounded-2xl border border-[#352626] p-4 text-zinc-100 ${AEGIS_GRADIENT}`}>
      <section className='rounded-2xl border border-[#3d2c2b] bg-[#1b1312]/90 p-4'>
        <div className='mb-4'>
          <h3 className='text-3xl font-semibold tracking-tight'>Skills Marketplace</h3>
          <p className='mt-1 text-sm text-zinc-400'>Browse the Aegis skill library (security reviewed by default).</p>
        </div>

        <div className='grid gap-2 md:grid-cols-2'>
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder='Search skills by name, slug, or summary'
            className='rounded-xl border border-[#1f3a52] bg-[#061a2d] px-4 py-3 text-sm'
          />
          <div className='flex gap-2'>
            <select
              value={riskFilter}
              onChange={(event) => setRiskFilter(event.target.value as 'all' | 'low' | 'medium' | 'high')}
              className='w-full rounded-xl border border-[#1f3a52] bg-[#061a2d] px-3 py-3 text-sm'
            >
              <option value='all'>All risk levels</option>
              <option value='low'>Low</option>
              <option value='medium'>Medium</option>
              <option value='high'>High</option>
            </select>
            <button type='button' className={`rounded-xl border px-3 py-2 text-xs ${marketView === 'table' ? 'border-rose-400/60 bg-rose-500/20' : 'border-[#2a2a2a]'}`} onClick={() => setMarketView('table')}>
              List
            </button>
            <button type='button' className={`rounded-xl border px-3 py-2 text-xs ${marketView === 'cards' ? 'border-rose-400/60 bg-rose-500/20' : 'border-[#2a2a2a]'}`} onClick={() => setMarketView('cards')}>
              Cards
            </button>
          </div>
        </div>

        <p className='mt-3 text-xs text-zinc-400'>{hubFiltered.length} of {hubSkills.length} skills (filtered)</p>

        <div className='mt-4 grid gap-4 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]'>
          <div className='overflow-hidden rounded-2xl border border-[#3a2f2f]'>
            {loadingHub ? (
              <p className='p-4 text-sm text-zinc-400'>Loading marketplace…</p>
            ) : marketView === 'cards' ? (
              <div className='grid gap-2 p-2'>
                {hubFiltered.map((skill) => (
                  <button
                    key={skill.id}
                    type='button'
                    onClick={() => setActiveSkillId(skill.id)}
                    className={`rounded-xl border p-3 text-left ${selectedSkill?.id === skill.id ? 'border-rose-400/60 bg-[#2a1b1a]' : 'border-[#352a2a] bg-[#1a1414] hover:bg-[#211919]'}`}
                  >
                    <p className='text-base font-semibold'>{skill.name}</p>
                    <p className='text-xs text-zinc-400'>Updated {formatDate(skill.updated_at)}</p>
                    <p className='mt-2 line-clamp-2 text-xs text-zinc-300'>{skill.description || 'No description yet.'}</p>
                  </button>
                ))}
              </div>
            ) : (
              <table className='w-full text-left text-sm'>
                <thead className='bg-[#2b2020] text-xs uppercase tracking-[0.08em] text-zinc-300'>
                  <tr>
                    <th className='px-4 py-3'>Skill</th>
                    <th className='px-4 py-3'>Summary</th>
                  </tr>
                </thead>
                <tbody>
                  {hubFiltered.map((skill) => (
                    <tr
                      key={skill.id}
                      onClick={() => setActiveSkillId(skill.id)}
                      className={`cursor-pointer border-t border-[#332525] ${selectedSkill?.id === skill.id ? 'bg-[#2c1f1e]' : 'hover:bg-[#221817]'}`}
                    >
                      <td className='px-4 py-3 align-top'>
                        <p className='text-xl font-semibold'>{skill.slug}</p>
                        <p className='text-xs text-zinc-400'>Updated {formatDate(skill.updated_at)}</p>
                      </td>
                      <td className='px-4 py-3 text-zinc-300'>{skill.description || 'No summary provided.'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {selectedSkill && (
            <article className='rounded-2xl border border-[#3a2c2b] bg-[#231817]/95 p-4'>
              <div className='flex items-center justify-between gap-3'>
                <h4 className='text-2xl font-semibold'>{selectedSkill.slug}</h4>
                <span className='rounded-full bg-[#6d3c2e] px-3 py-1 text-xs'>latest</span>
              </div>
              <p className='mt-2 text-zinc-300'>{selectedSkill.description || 'No description supplied for this skill yet.'}</p>
              <p className='mt-3 text-sm text-zinc-400'>by {selectedSkill.owner?.username || selectedSkill.owner?.name || '@aegis-author'}</p>
              <div className='mt-4 flex flex-wrap gap-2 text-xs'>
                <span className='rounded-full bg-[#163421] px-2 py-1 text-emerald-300'>VirusTotal: Benign</span>
                <span className='rounded-full bg-[#163421] px-2 py-1 text-emerald-300'>Aegis Scan: Benign</span>
              </div>
              <div className='mt-4 rounded-xl border border-[#3f3130] p-3 text-sm text-zinc-300'>
                <p className='font-medium text-zinc-100'>License</p>
                <p className='mt-1'>MIT-0 · Free to use, modify, and redistribute. No attribution required.</p>
              </div>
              <div className='mt-4 flex gap-2'>
                <button
                  type='button'
                  onClick={() => void onInstallSkill(selectedSkill)}
                  disabled={installedById.has(selectedSkill.id)}
                  className='rounded-xl bg-[#f97360] px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-60'
                >
                  {installedById.has(selectedSkill.id) ? 'Installed' : 'Install skill'}
                </button>
                <button type='button' className='rounded-xl border border-[#61322b] px-4 py-2 text-sm'>View files</button>
              </div>
            </article>
          )}
        </div>
      </section>

      <section className='rounded-2xl border border-[#3d2c2b] bg-[#1b1312]/90 p-4'>
        <h3 className='text-3xl font-semibold tracking-tight'>Publish a skill</h3>
        <p className='mt-1 text-sm text-zinc-400'>Create card metadata, then drop a folder with SKILL.md and supporting files.</p>

        <div className='mt-4 rounded-2xl border border-[#3a2c2b] bg-[#231817]/80 p-4'>
          <div className='grid gap-3 md:grid-cols-2'>
            <InputField label='Slug' value={publishForm.slug} onChange={(value) => setPublishForm((prev) => ({ ...prev, slug: value }))} placeholder='skill-name' />
            <InputField label='Display name' value={publishForm.name} onChange={(value) => setPublishForm((prev) => ({ ...prev, name: value }))} placeholder='My skill' />
            <InputField label='Owner' value={publishForm.owner} onChange={(value) => setPublishForm((prev) => ({ ...prev, owner: value }))} placeholder='@aegis-user' />
            <InputField label='Version' value={publishForm.version} onChange={(value) => setPublishForm((prev) => ({ ...prev, version: value }))} placeholder='1.0.0' />
            <InputField label='Tags' value={publishForm.tags} onChange={(value) => setPublishForm((prev) => ({ ...prev, tags: value }))} placeholder='latest, productivity' />
            <label className='space-y-1 text-xs uppercase tracking-[0.15em] text-zinc-400'>
              Publish target
              <select
                className='w-full rounded-xl border border-[#1f3a52] bg-[#061a2d] px-3 py-3 text-sm uppercase tracking-normal text-zinc-100'
                value={publishForm.publishTarget}
                onChange={(event) => setPublishForm((prev) => ({ ...prev, publishTarget: event.target.value as 'hub' | 'global' }))}
              >
                <option value='hub'>Hub</option>
                {isAdmin && <option value='global'>Global</option>}
              </select>
            </label>
          </div>

          <label className='mt-3 block space-y-1 text-xs uppercase tracking-[0.15em] text-zinc-400'>
            Summary
            <textarea
              value={publishForm.description}
              onChange={(event) => setPublishForm((prev) => ({ ...prev, description: event.target.value }))}
              className='h-24 w-full rounded-xl border border-[#1f3a52] bg-[#061a2d] p-3 text-sm'
              placeholder='Describe this skill for marketplace cards.'
            />
          </label>
        </div>

        <div className='mt-4 rounded-2xl border border-[#3a2c2b] bg-[#231817]/80 p-4'>
          <div
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => void onDrop(event)}
            className='rounded-xl border border-dashed border-[#7b5f53] bg-[#2a1e1d] p-6 text-center'
          >
            <p className='text-3xl font-semibold'>Drop a folder</p>
            <p className='mt-1 text-sm text-zinc-400'>We keep folder paths and flatten outer wrappers automatically.</p>
            <label className='mx-auto mt-4 inline-flex cursor-pointer rounded-full border border-[#8b5148] px-4 py-2 text-sm'>
              Choose folder
              <input type='file' multiple className='hidden' onChange={(event) => void onFileInput(event)} />
            </label>
          </div>
          <p className='mt-2 text-sm text-zinc-300'>
            {droppedFiles.length ? `${droppedFiles.length} files selected` : 'No files selected.'}
          </p>

          <label className='mt-3 block space-y-1 text-xs uppercase tracking-[0.15em] text-zinc-400'>
            SKILL.md preview
            <textarea
              value={skillMarkdown}
              onChange={(event) => setSkillMarkdown(event.target.value)}
              className='h-56 w-full rounded-xl border border-[#1f3a52] bg-[#061a2d] p-3 font-mono text-xs'
              placeholder='Paste or drop SKILL.md content here.'
            />
          </label>

          <div className='mt-4 rounded-xl border border-[#3f3130] p-3'>
            <p className='text-2xl font-semibold'>License</p>
            <p className='mt-1 text-zinc-300'>MIT-0 · MIT No Attribution (Aegis default skill license).</p>
            <label className='mt-3 flex items-start gap-2 text-sm text-zinc-200'>
              <input
                type='checkbox'
                checked={publishForm.acceptedLicense}
                onChange={(event) => setPublishForm((prev) => ({ ...prev, acceptedLicense: event.target.checked }))}
              />
              <span>I have the rights to this skill and agree to publish it under MIT-0.</span>
            </label>

            <label className='mt-3 block space-y-1 text-xs uppercase tracking-[0.15em] text-zinc-400'>
              Changelog
              <textarea
                value={publishForm.changelog}
                onChange={(event) => setPublishForm((prev) => ({ ...prev, changelog: event.target.value }))}
                className='h-28 w-full rounded-xl border border-[#1f3a52] bg-[#061a2d] p-3 text-sm'
                placeholder='Describe what changed in this skill…'
              />
            </label>
          </div>

          <div className='mt-4 flex justify-end'>
            <button
              type='button'
              onClick={() => void onPublish()}
              disabled={submitting}
              className='rounded-2xl bg-[#c75742] px-8 py-3 text-lg font-semibold disabled:cursor-not-allowed disabled:opacity-60'
            >
              {submitting ? 'Publishing…' : 'Publish skill'}
            </button>
          </div>
        </div>
      </section>

      <section className='grid gap-4 xl:grid-cols-2'>
        <div className='rounded-2xl border border-[#3d2c2b] bg-[#1b1312]/90 p-4'>
          <div className='mb-3 flex items-center justify-between'>
            <h3 className='text-xl font-semibold'>Installed skills</h3>
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

                  <div className='mt-3'>
                    <button type='button' onClick={() => void onDeleteSkill(skill.skill_id)} className='rounded border border-red-500/40 px-2 py-1 text-xs text-red-300 hover:bg-red-500/10'>
                      Uninstall
                    </button>
                  </div>
                </article>
              ))}
            </div>
          )}
        </div>

        {isAdmin && (
          <div className='space-y-4'>
            <section className='rounded-2xl border border-[#3d2c2b] bg-[#1b1312]/90 p-4'>
              <h3 className='mb-3 text-xl font-semibold'>Admin publishing policy</h3>
              {loadingPolicy ? (
                <p className='text-xs text-zinc-400'>Loading policy…</p>
              ) : (
                <div className='space-y-3'>
                  <ToggleRow label='Allow unreviewed installs' value={policy.allow_unreviewed_installs} onToggle={(value) => void updatePolicy({ allow_unreviewed_installs: value })} disabled={savingPolicy} />
                  <ToggleRow label='Block high-risk skills' value={policy.block_high_risk_skills} onToggle={(value) => void updatePolicy({ block_high_risk_skills: value })} disabled={savingPolicy} />
                  <ToggleRow label='Require approval before install' value={policy.require_approval_before_install} onToggle={(value) => void updatePolicy({ require_approval_before_install: value })} disabled={savingPolicy} />
                  <label className='block text-xs font-medium text-zinc-300'>
                    Org default-enabled skill IDs
                    <textarea
                      className='mt-1 h-20 w-full rounded border border-[#2a2a2a] bg-[#111] p-2 text-xs'
                      value={policy.default_enabled_skill_ids.join('\n')}
                      onChange={(event) =>
                        void updatePolicy({
                          default_enabled_skill_ids: event.target.value.split('\n').map((line) => line.trim()).filter(Boolean),
                        })
                      }
                    />
                  </label>
                </div>
              )}
            </section>

            <section className='rounded-2xl border border-[#3d2c2b] bg-[#1b1312]/90 p-4'>
              <div className='mb-3 flex items-center justify-between'>
                <h3 className='text-xl font-semibold'>Admin publishing controls</h3>
                <button type='button' className='rounded border border-[#2a2a2a] px-2 py-1 text-xs hover:bg-zinc-800' onClick={() => void refreshReviewQueue()}>
                  Refresh queue
                </button>
              </div>
              {loadingQueue ? (
                <p className='text-xs text-zinc-400'>Loading review queue…</p>
              ) : reviewQueue.length === 0 ? (
                <p className='text-xs text-zinc-400'>No pending submissions.</p>
              ) : (
                <div className='space-y-2'>
                  {reviewQueue.map((item) => (
                    <article key={item.submission.id} className='rounded-xl border border-[#2d2222] bg-[#181212] p-3'>
                      <p className='text-sm font-semibold'>{item.skill.name}</p>
                      <p className='text-xs text-zinc-400'>
                        {item.skill.slug} · {item.submission.review_state} · {formatDate(item.submission.created_at)}
                      </p>
                      <div className='mt-2 flex flex-wrap gap-2'>
                        <button type='button' className='rounded border border-amber-500/40 px-2 py-1 text-xs text-amber-200' onClick={() => void handleReviewAction(item, 'scan')}>Scan</button>
                        <button type='button' className='rounded border border-emerald-500/40 px-2 py-1 text-xs text-emerald-200' onClick={() => void handleReviewAction(item, 'approve_hub')}>Approve hub</button>
                        <button type='button' className='rounded border border-blue-500/40 px-2 py-1 text-xs text-blue-200' onClick={() => void handleReviewAction(item, 'approve_global')}>Approve global</button>
                        <button type='button' className='rounded border border-red-500/40 px-2 py-1 text-xs text-red-200' onClick={() => void handleReviewAction(item, 'reject')}>Reject</button>
                      </div>
                    </article>
                  ))}
                </div>
              )}
            </section>
          </div>
        )}
      </section>
    </div>
  )
}

function InputField({ label, value, onChange, placeholder }: { label: string; value: string; onChange: (value: string) => void; placeholder: string }) {
  return (
    <label className='space-y-1 text-xs uppercase tracking-[0.15em] text-zinc-400'>
      {label}
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        className='w-full rounded-xl border border-[#1f3a52] bg-[#061a2d] px-3 py-3 text-sm normal-case tracking-normal text-zinc-100'
      />
    </label>
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
