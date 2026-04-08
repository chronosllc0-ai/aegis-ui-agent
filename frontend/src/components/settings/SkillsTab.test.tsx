import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { SkillsTab } from './SkillsTab'

const toastError = vi.fn()

vi.mock('../../hooks/useSkills', () => ({
  useSkills: () => ({
    installed: [
      {
        skill_id: 'installed-1',
        slug: 'installed-1',
        name: 'Installed One',
        version_id: 'version-1',
        enabled: true,
        risk_label: 'clean',
      },
    ],
    setInstalled: vi.fn(),
    loadingInstalled: false,
    toggleSkill: vi.fn(),
    uninstallSkill: vi.fn(),
    refreshInstalled: vi.fn(async () => undefined),
    installSkill: vi.fn(async () => {
      throw new Error('Install blocked: malicious scan result')
    }),
    hubSkills: [{ id: 'market-1', name: 'Market One', slug: 'market-one', description: 'desc', risk_label: 'malicious' }],
    loadingHub: false,
    refreshHub: vi.fn(async () => undefined),
    submitSkill: vi.fn(async () => undefined),
    policy: { allow_unreviewed_installs: false, block_high_risk_skills: true, require_approval_before_install: false, default_enabled_skill_ids: [] },
    loadingPolicy: false,
    savePolicy: vi.fn(),
    reviewQueue: [],
    loadingQueue: false,
    refreshReviewQueue: vi.fn(async () => undefined),
    reviewSubmission: vi.fn(async () => undefined),
    scanSubmission: vi.fn(async () => undefined),
  }),
}))

vi.mock('../../context/useSettingsContext', () => ({
  useSettingsContext: () => ({ patchSettings: vi.fn() }),
}))

vi.mock('../../hooks/useToast', () => ({
  useToast: () => ({ success: vi.fn(), error: toastError }),
}))

vi.mock('../skills-hub/SubmissionForm', () => ({ SubmissionForm: () => <div /> }))
vi.mock('../skills-hub/SubmissionStatusTimeline', () => ({ SubmissionStatusTimeline: () => <div /> }))
vi.mock('../skills-hub/ReviewQueue', () => ({ ReviewQueue: () => <div /> }))

describe('SkillsTab marketplace install UX', () => {
  beforeEach(() => {
    toastError.mockReset()
  })

  it('shows install failure toast when marketplace install is blocked', async () => {
    render(<SkillsTab role='admin' />)
    await waitFor(() => expect(screen.getAllByText('market-one').length).toBeGreaterThan(0))

    fireEvent.click(screen.getByRole('button', { name: 'Install skill' }))
    await waitFor(() => {
      expect(toastError).toHaveBeenCalledWith('Failed to install skill', 'Install blocked: malicious scan result')
    })
  })
})
