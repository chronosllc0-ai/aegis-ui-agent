import { describe, expect, it } from 'vitest'

import { filterSkillsByStatus, getSkillStatusBadge, normalizeSkillSubmissionStatus } from './skillSubmissionStatus'

describe('skill submission status helpers', () => {
  it('maps legacy backend states to current status vocabulary', () => {
    expect(normalizeSkillSubmissionStatus('approved_hub')).toBe('published_hub')
    expect(normalizeSkillSubmissionStatus('pending_scan')).toBe('scanning')
    expect(normalizeSkillSubmissionStatus('pending_review')).toBe('review')
  })

  it('returns badge metadata for rendering status badges', () => {
    const badge = getSkillStatusBadge('published_global')
    expect(badge.label).toBe('Published (Global)')
    expect(badge.className).toContain('violet')
  })

  it('filters list by normalized status value', () => {
    const skills = [
      { id: '1', status: 'draft' },
      { id: '2', status: 'approved_hub' },
      { id: '3', status: 'published_global' },
    ]
    const filtered = filterSkillsByStatus(skills, 'published_hub')
    expect(filtered.map((row) => row.id)).toEqual(['2'])
  })
})
