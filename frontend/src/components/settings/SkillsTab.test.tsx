import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { SkillsTab } from './SkillsTab'

const apiRequestMock = vi.fn()
const toastError = vi.fn()

vi.mock('../../lib/api', () => ({
  apiRequest: (...args: unknown[]) => apiRequestMock(...args),
}))

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
    policy: { allow_unreviewed_installs: false, block_high_risk_skills: true, require_approval_before_install: false, default_enabled_skill_ids: [] },
    loadingPolicy: false,
    savePolicy: vi.fn(),
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
    apiRequestMock.mockReset()
    toastError.mockReset()
    apiRequestMock.mockImplementation(async (path: string) => {
      if (path === '/api/skills/hub') {
        return { skills: [{ id: 'market-1', name: 'Market One', slug: 'market-one', description: 'desc', risk_label: 'malicious' }] }
      }
      if (path.includes('/install')) {
        throw new Error('Install blocked: malicious scan result')
      }
      if (path.includes('/transition')) {
        return { submission: { id: 's1', current_state: 'draft' }, allowed_transitions: [] }
      }
      return {}
    })
  })

  it('renders marketplace risk tag and shows blocked install message', async () => {
    render(<SkillsTab role='admin' />)
    await waitFor(() => expect(screen.getByText('malicious')).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: 'Install' }))
    await waitFor(() => expect(screen.getByText(/Install blocked: malicious scan result/i)).toBeInTheDocument())
    expect(toastError).toHaveBeenCalled()
  })
})
